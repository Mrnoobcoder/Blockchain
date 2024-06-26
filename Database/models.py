from sqlalchemy import create_engine,Integer, Column, String, Float, ForeignKey, JSON, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker
import inquirer
import ecdsa


# Defining a base class for declarative models
Base = declarative_base()


class Wallet(Base):
    __tablename__ = 'wallets'
    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False)
    authorize_address_to_create_money = Column(Boolean, default=False)
    utxos = relationship('Utxo', back_populates='wallet')
   
    def __init__(self, address=None):
        self.address = address
        if address:  
            self.create()

    def create(self):
        if not self.address:
            print("Cannot create wallet without an address.")
            return

        # Inserting a row into the "wallets" table
        session.add(self)  # Add the current instance to the session
        session.commit()
        print(f"Wallet inserted: Address - {self.address}")

    def authorize_address_to_create_money(self, address):
        # Fetch a wallet based on the provided address
        wallet = self.fetch_wallet_by_address(address)
        if wallet:
            wallet.authorize_address_to_create_money = True
            # Do not commit here, only update the attribute
            print(f"Wallet {wallet.address} authorized to create money.")
            session.commit()
        else:
            print(f"Wallet with the address {address} not found.")

    @staticmethod
    def fetch_wallet_by_address(address):
        # Fetch a wallet based on the provided address
        return session.query(Wallet).filter_by(address=address).first()


# Defining the UTXO model
class Utxo(Base):
    __tablename__ = 'utxos'
    id = Column(Integer, primary_key=True)
    amount = Column(Float, nullable=False)
    wallet_id = Column(Integer, ForeignKey('wallets.id'))#Represent the wallet where the utxo is created
    #wallet retpresent wallet(id and address) associated with the utxo id
    wallet = relationship('Wallet', back_populates='utxos')# can access wallets associated with the utxo
    transaction_id = Column(Integer, ForeignKey('transactions.id'))#Represent the transaction during which the utxo is created
    #transaction represent transaction data associated with the utxo id
    transaction = relationship('Transaction', back_populates='utxos')#can access transactions associated with the utxo
    
    @staticmethod
    def create_utxo(wallet_id, transaction_id, amount):
        # Insert a row into the 'utxos' table
        utxo = Utxo(wallet_id=wallet_id, transaction_id=transaction_id, amount=amount)
        session.add(utxo)
        session.commit()
        print(f"UTXO inserted: Wallet ID - {wallet_id}, Amount - {amount}")
        return utxo
    
    @staticmethod
    def fetch_utxos_by_wallet(wallet_id):
        # Fetch UTXOs based on wallet ID
        return session.query(Utxo).filter(Utxo.wallet_id == wallet_id).all()
    
    @staticmethod
    def fetch_available_utxos(source_wallet):
        #Fetching all the utxos associated will the wallet
        source_utxos = Utxo.fetch_utxos_by_wallet(source_wallet.id)
        return [utxo for utxo in source_utxos if not Transaction.is_utxo_spent(utxo.id)]

    @staticmethod
    def calculate_total_balance(utxos):
        #Calculating total balance of all the utxos
        return sum(utxo.amount for utxo in utxos)
    
    #Get the list of used UTXOs. If it doesn't exist, create an empty list.
    @classmethod
    def _get_used_utxos(cls):
        if not hasattr(cls, '_used_utxos'):
            cls._used_utxos = []
        return cls._used_utxos

    #Add a UTXO to the list of used UTXOs.
    @classmethod
    def _add_used_utxo(cls, utxo):
        cls._get_used_utxos().append(utxo)

    #Clear the list of used UTXOs.
    @classmethod
    def _clear_used_utxos(cls):
        cls._get_used_utxos().clear()

    #The following method is for selecting the particular utxos for transaction
    @classmethod
    def show_utxos_and_select(cls, available_utxos, transfer_amount):
        cls._clear_used_utxos()

        # Accessing used utxos using class method
        filtered_utxos = [utxo for utxo in available_utxos if utxo not in cls._get_used_utxos()]
        
        #utxo information of the source address
        utxos_info = [
            (str(utxo.id), f"UTXO ID: {utxo.id}, Amount: {utxo.amount}")
            for utxo in filtered_utxos
        ]
        #total available amount to the source address
        total_available_amount = sum(utxo.amount for utxo in filtered_utxos)

        print(f"\nAmount to be transferred: {transfer_amount}")
        print(f"Total available amount in UTXOs: {total_available_amount}")
        print("\nAvailable UTXOs:")

        for utxo_info in utxos_info:
            print(utxo_info[1])  # Print UTXO information
        #Asks the user to select the utxos
        questions = [
            inquirer.Checkbox(
                'utxos',
                message="Select UTXOs to cover the transfer amount:",
                choices=utxos_info
            )
        ]

        answers = inquirer.prompt(questions)
        selected_utxos_ids = answers['utxos']

        # Store used UTXOs for persistence
        cls._add_used_utxo(utxo for utxo in filtered_utxos if utxo.id in selected_utxos_ids)

        # Corrected line to create utxos_dict
        utxos_dict = {utxo_id: utxo for utxo_id, utxo in zip(selected_utxos_ids, filtered_utxos)}
        
        #utxos selected by the users to cover the transfer amount
        selected_utxos = [utxos_dict[utxo_id] for utxo_id in selected_utxos_ids]
        #total selected amount form the selected utxos
        total_selected_amount = sum(float(utxo.amount) for utxo in selected_utxos)
        
        return selected_utxos, total_selected_amount




# Defining the Transaction model
class Transaction(Base):
    __tablename__ = 'transactions'
    id = Column(Integer, primary_key=True)
    #inputs contain the utxos(utxo id) used as input
    inputs = Column(JSON)
    #outputs contain destination address and amount
    outputs = Column(JSON, nullable=False)
    signatures = Column(JSON, nullable=False)
    create_money = Column(Boolean, nullable=False)
    #Here utxos represent all the utxos associated with transaction id
    utxos = relationship('Utxo', back_populates='transaction')# can access utxos associated with the transaction

    @staticmethod
    def create_transaction(inputs, outputs, signatures, create_money):
        # Extract Utxo IDs from the list of Utxo objects
        input_ids = [utxo.id for utxo in inputs]

        # Insert a row into the 'transactions' table
        transaction = Transaction(
            inputs=input_ids,  # Use only the IDs instead of the Utxo objects
            outputs=outputs,
            signatures=signatures,
            create_money=create_money,
        )
        session.add(transaction)
        session.commit()
        print(f'Transaction inserted')
        return transaction
    
    @classmethod
    def verify_create_money_inputs(cls, authorized_address, destination_address, amount):
        error = None
        if not cls.is_valid_wallet_address(authorized_address):
            error = f"Invalid authorized address: {authorized_address}"
            return False, error
        if not cls.is_valid_wallet_address(destination_address):
            error = f"Invalid destination address: {destination_address}"
            return False, error
        if not isinstance(amount, (int, float)) or amount <= 0:
            error = f"Invalid amount: {amount}"
            return False, error
        if session.query(Wallet).filter_by(address=authorized_address).count() == 0:
            error = f"{authorized_address} is not authorized to create money"
            return False, error
        return True, None

    @staticmethod
    def is_valid_wallet_address(address):
        return session.query(Wallet).filter_by(address=address).count()

    @staticmethod
    def sign_transaction(private_key, transaction_data):
        signature = private_key.sign(transaction_data)
        return signature
    
    @staticmethod
    def verify_signature(public_key, transaction_data_bytes, signature):
        try:
            # Verify the signature
            public_key.verify(signature, transaction_data_bytes)
            return True
        except ecdsa.BadSignatureError:
            return False
    
    @staticmethod
    def is_utxo_spent(utxo_id):
        # Check if a UTXO is spent by looking at transactions' inputs
        return session.query(Transaction).filter(Transaction.inputs.contains([utxo_id])).count() > 0
    
    #The following code verifies the source addresses and transfer details list
    @classmethod
    def validate_transfer(cls, source_addresses, transfer_details_list):
        for transfer_details in transfer_details_list:
            source_address = transfer_details.get('source_address')
            destination_address = transfer_details.get('destination_address')

            if source_address not in source_addresses:
                return False, f"Invalid source address: {source_address}"

            if not cls.is_valid_wallet_address(destination_address):
                return False, f"Invalid destination address: {destination_address}"

            amount = transfer_details.get('amount')
            if not isinstance(amount, (int, float)) or amount <= 0:
                return False, f"Invalid amount for address {destination_address}: {amount}"

        return True, None
    

# Creating an SQLite database
engine = create_engine('sqlite:///wallet.db', echo=True)

# Create the tables in the database
Base.metadata.create_all(bind=engine)

# Create a session to interact with the database
Session = sessionmaker(bind=engine)
session = Session()