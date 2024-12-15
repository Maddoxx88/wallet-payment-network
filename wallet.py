import getpass
import re
from datetime import datetime, timedelta

import mysql.connector
import psycopg2
from mysql.connector import Error
from dotenv import load_dotenv
import os

load_dotenv()

# Access variables
db_host = os.getenv("DB_HOST")
db_name = os.getenv("DB_NAME")
db_user = os.getenv("DB_USER")
db_password = os.getenv("DB_PASSWORD")
db_port = os.getenv("DB_PORT")

class WalletPaymentNetwork:
    def __init__(self):
        # Database connection parameters 
        # Replace with your actual database connection details
        self.db_params = {
            'database': db_name,
            'user': db_user,
            'password': db_password,
            'host': db_host,
            'port': db_port
        }
        self.current_user_ssn = None

    def connect_db(self):
        """Establish database connection"""
        try:
            # Attempt to connect using mysql.connector
            connection = mysql.connector.connect(**self.db_params)
            return connection
        except Error as error:
            print("Error connecting to MySQL database:", error)
            return None

    def validate_email(self, email):
        """Validate email format"""
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_regex, email) is not None

    def validate_phone(self, phone):
        """Validate phone number format"""
        phone_regex = r'^\+?1?\d{10,14}$'
        return re.match(phone_regex, phone) is not None

    def login(self):
        """User Login"""
        try:
            conn = self.connect_db()
            if not conn:
                return False

            cursor = conn.cursor()
            
            while True:
                ssn = input("Enter SSN (XXX-XX-XXXX): ")
                
                # Validate SSN format
                if not re.match(r'^\d{3}-\d{2}-\d{4}$', ssn):
                    print("Invalid SSN format. Please use XXX-XX-XXXX.")
                    continue

                query = """
                SELECT Name, Confirmed 
                FROM WALLET_ACCOUNT 
                WHERE SSN = %s
                """
                cursor.execute(query, (ssn,))
                user = cursor.fetchone()

                if user:
                    name, confirmed = user
                    if not confirmed:
                        print("Account is not confirmed. Please contact support.")
                        return False
                    
                    self.current_user_ssn = ssn
                    print(f"Welcome, {name}!")
                    return True
                else:
                    print("User not found. Would you like to register? (Y/N)")
                    choice = input().upper()
                    if choice == 'Y':
                        self.register_account()
                        return False

        except psycopg2.Error as e:
            print("Database error:", e)
            return False
        finally:
            if conn:
                cursor.close()
                conn.close()

    def register_account(self):
        """Register a new wallet account"""
        try:
            conn = self.connect_db()
            if not conn:
                return

            cursor = conn.cursor()

            # Collect user details
            ssn = input("Enter SSN (XXX-XX-XXXX): ")
            name = input("Enter Full Name: ")
            email = input("Enter Email Address: ")
            phone = input("Enter Phone Number (+1XXXXXXXXXX): ")

            # Validate inputs
            if not re.match(r'^\d{3}-\d{2}-\d{4}$', ssn):
                print("Invalid SSN format.")
                return

            if not self.validate_email(email):
                print("Invalid email format.")
                return

            if not self.validate_phone(phone):
                print("Invalid phone number format.")
                return

            # Insert new account
            insert_account_query = """
            INSERT INTO WALLET_ACCOUNT 
            (SSN, Name, Confirmed, Email, Phone, Balance) 
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            
            # Generate a simple wallet account ID
            wallet_account_id = f"WLET{ssn.replace('-', '')}"

            cursor.execute(insert_account_query, (
                ssn, name, False, email, phone, 0.00
            ))

            # Insert email and phone
            insert_email_query = """
            INSERT INTO EMAIL_ADDRESS 
            (SSN, EmailAddress, Is_Primary, Verified) 
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_email_query, (ssn, email, True, False))

            insert_phone_query = """
            INSERT INTO PHONE 
            (SSN, PhoneNumber, Is_Primary, Verified) 
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_phone_query, (ssn, phone, True, False))

            conn.commit()
            print("Account registered successfully. Awaiting confirmation.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Registration failed:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def send_money(self):
        """Send money to another wallet user"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Get recipient details
            recipient_id = input("Enter recipient's email or phone: ")
            amount = float(input("Enter amount to send: "))

            # Find recipient's SSN
            find_recipient_query = """
            SELECT wa.SSN 
            FROM WALLET_ACCOUNT wa
            LEFT JOIN EMAIL_ADDRESS ea ON wa.SSN = ea.SSN
            LEFT JOIN PHONE p ON wa.SSN = p.SSN
            WHERE ea.EmailAddress = %s OR p.PhoneNumber = %s
            """
            cursor.execute(find_recipient_query, (recipient_id, recipient_id))
            recipient_ssn = cursor.fetchone()

            if not recipient_ssn:
                print("Recipient not found.")
                return

            recipient_ssn = recipient_ssn[0]

            # Create send transaction
            insert_transaction_query = """
            INSERT INTO SEND_TRANSACTION 
            (Sender_SSN, Recipient_SSN, Amount, Memo, Status) 
            VALUES (%s, %s, %s, %s, %s)
            """
            memo = input("Enter transaction memo (optional): ")
            cursor.execute(insert_transaction_query, (
                self.current_user_ssn, 
                recipient_ssn, 
                amount, 
                memo or "Transfer", 
                'COMPLETED'
            ))

            # Update balances
            update_sender_balance = """
            UPDATE WALLET_ACCOUNT 
            SET Balance = Balance - %s 
            WHERE SSN = %s
            """
            cursor.execute(update_sender_balance, (amount, self.current_user_ssn))

            update_recipient_balance = """
            UPDATE WALLET_ACCOUNT 
            SET Balance = Balance + %s 
            WHERE SSN = %s
            """
            cursor.execute(update_recipient_balance, (amount, recipient_ssn))

            conn.commit()
            print(f"Successfully sent ${amount} to {recipient_id}")

        except psycopg2.Error as e:
            conn.rollback()
            print("Transaction failed:", e)
        except ValueError:
            print("Invalid amount entered.")
        finally:
            if conn:
                cursor.close()
                conn.close()

    def request_money(self):
        """Request money from another wallet user"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Get recipient details
            recipient_id = input("Enter recipient's email or phone: ")
            amount = float(input("Enter amount to request: "))

            # Find recipient's SSN
            find_recipient_query = """
            SELECT wa.SSN 
            FROM WALLET_ACCOUNT wa
            LEFT JOIN EMAIL_ADDRESS ea ON wa.SSN = ea.SSN
            LEFT JOIN PHONE p ON wa.SSN = p.SSN
            WHERE ea.EmailAddress = %s OR p.PhoneNumber = %s
            """
            cursor.execute(find_recipient_query, (recipient_id, recipient_id))
            recipient_ssn = cursor.fetchone()

            if not recipient_ssn:
                print("Recipient not found.")
                return

            recipient_ssn = recipient_ssn[0]

            # Create request transaction
            insert_request_query = """
            INSERT INTO REQUEST_TRANSACTION 
            (Sender_SSN, Recipient_SSN, Amount, Memo, Status) 
            VALUES (%s, %s, %s, %s, %s)
            """
            memo = input("Enter request memo (optional): ")
            cursor.execute(insert_request_query, (
                recipient_ssn, 
                self.current_user_ssn, 
                amount, 
                memo or "Money Request", 
                'PENDING'
            ))

            conn.commit()
            print(f"Request for ${amount} sent to {recipient_id}")

        except psycopg2.Error as e:
            conn.rollback()
            print("Request failed:", e)
        except ValueError:
            print("Invalid amount entered.")
        finally:
            if conn:
                cursor.close()
                conn.close()

    def view_statements(self):
        """View transaction statements"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Get date range
            start_date = input("Enter start date (YYYY-MM-DD): ")
            end_date = input("Enter end date (YYYY-MM-DD): ")

            start_date_formatted = f"{start_date} 00:00:00"
            end_date_formatted = f"{end_date} 23:59:59"

            # Total sent and received
            total_sent_query = """
            SELECT SUM(Amount) as total_sent
            FROM SEND_TRANSACTION
            WHERE Sender_SSN = %s AND Date_Time_Initiated BETWEEN %s AND %s
            """
            cursor.execute(total_sent_query, (self.current_user_ssn, start_date_formatted, end_date_formatted))
            total_sent = cursor.fetchone()[0] or 0

            total_received_query = """
            SELECT SUM(Amount) as total_received
            FROM SEND_TRANSACTION
            WHERE Recipient_SSN = %s AND Date_Time_Initiated BETWEEN %s AND %s
            """
            cursor.execute(total_received_query, (self.current_user_ssn, start_date_formatted, end_date_formatted))
            total_received = cursor.fetchone()[0] or 0

            print("\n--- Transaction Statement ---")
            print(f"Period: {start_date} to {end_date}")
            print(f"Total Amount Sent: ${total_sent:.2f}")
            print(f"Total Amount Received: ${total_received:.2f}")

            # Monthly breakdown
            monthly_breakdown_query = """
            SELECT 
                EXTRACT(YEAR FROM Date_Time_Initiated) as year,
                EXTRACT(MONTH FROM Date_Time_Initiated) as month,
                SUM(CASE WHEN Sender_SSN = %s THEN Amount ELSE 0 END) as total_sent,
                SUM(CASE WHEN Recipient_SSN = %s THEN Amount ELSE 0 END) as total_received
            FROM SEND_TRANSACTION
            WHERE Date_Time_Initiated BETWEEN %s AND %s
            GROUP BY year, month
            ORDER BY year, month
            """
            cursor.execute(monthly_breakdown_query, (
                self.current_user_ssn, 
                self.current_user_ssn, 
                start_date_formatted, 
                end_date_formatted
            ))
            
            print("\nMonthly Breakdown:")
            for row in cursor.fetchall():
                print(f"{int(row[0])}-{int(row[1]):02d}: Sent ${row[2]:.2f}, Received ${row[3]:.2f}")

        except psycopg2.Error as e:
            print("Statement retrieval failed:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def manage_account(self):
        """Account management menu"""
        while True:
            print("\n--- Account Management ---")
            print("1. Modify Personal Details")
            print("2. Add Email Address")
            print("3. Remove Email Address")
            print("4. Add Phone Number")
            print("5. Remove Phone Number")
            print("6. Add Bank Account")
            print("7. Remove Bank Account")
            print("8. Return to Main Menu")

            choice = input("Enter your choice: ")

            if choice == '1':
                self.modify_personal_details()
            elif choice == '2':
                self.add_email()
            elif choice == '3':
                self.remove_email()
            elif choice == '4':
                self.add_phone()
            elif choice == '5':
                self.remove_phone()
            elif choice == '6':
                self.add_bank_account()
            elif choice == '7':
                self.remove_bank_account()
            elif choice == '8':
                break
            else:
                print("Invalid choice. Try again.")

    def modify_personal_details(self):
        """Modify user's personal details"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Get new details
            name = input("Enter new name (leave blank to keep current): ")
            email = input("Enter new email id (leave blank to keep current): ")
            
            if name:
                update_query = """
                UPDATE WALLET_ACCOUNT
                SET Name = %s
                WHERE SSN = %s
                """
                cursor.execute(update_query, (name, self.current_user_ssn))
                conn.commit()
                print("Name updated successfully.")
            
            if email:
                update_query = """
                UPDATE WALLET_ACCOUNT
                SET Email = %s
                WHERE SSN = %s
                """
                cursor.execute(update_query, (email, self.current_user_ssn))
                conn.commit()
                print("Email ID updated successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Update failed:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def add_email(self):
        """Add a new email address"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        email = input("Enter email address: ")
        if not self.validate_email(email):
            print("Invalid email format.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            insert_email_query = """
            INSERT INTO EMAIL_ADDRESS 
            (SSN, EmailAddress, Is_Primary, Verified) 
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_email_query, (
                self.current_user_ssn, email, False, False
            ))
            conn.commit()
            print("Email address added successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to add email:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def remove_email(self):
        """Remove an email address"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Retrieve user's email addresses
            get_emails_query = """
            SELECT EmailAddress, Is_Primary 
            FROM EMAIL_ADDRESS 
            WHERE SSN = %s
            """
            cursor.execute(get_emails_query, (self.current_user_ssn,))
            emails = cursor.fetchall()

            if not emails:
                print("No email addresses found.")
                return

            print("Your email addresses:")
            for i, (email, is_primary) in enumerate(emails, 1):
                primary_status = " (Primary)" if is_primary else ""
                print(f"{i}. {email}{primary_status}")

            choice = input("Enter the number of the email to remove (or press Enter to cancel): ")
            
            if not choice:
                return

            try:
                email_index = int(choice) - 1
                email_to_remove = emails[email_index][0]
                is_primary = emails[email_index][1]

                if is_primary:
                    print("Cannot remove primary email address.")
                    return

                # Remove email address
                remove_email_query = """
                DELETE FROM EMAIL_ADDRESS 
                WHERE SSN = %s AND EmailAddress = %s
                """
                cursor.execute(remove_email_query, (self.current_user_ssn, email_to_remove))
                conn.commit()
                print(f"Email {email_to_remove} removed successfully.")

            except (ValueError, IndexError):
                print("Invalid selection.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to remove email:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def add_phone(self):
        """Add a new phone number"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        phone = input("Enter phone number (+1XXXXXXXXXX): ")
        if not self.validate_phone(phone):
            print("Invalid phone number format.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            insert_phone_query = """
            INSERT INTO PHONE 
            (SSN, PhoneNumber, Is_Primary, Verified) 
            VALUES (%s, %s, %s, %s)
            """
            cursor.execute(insert_phone_query, (
                self.current_user_ssn, phone, False, False
            ))
            conn.commit()
            print("Phone number added successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to add phone number:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def remove_phone(self):
        """Remove a phone number"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Retrieve user's phone numbers
            get_phones_query = """
            SELECT PhoneNumber, Is_Primary 
            FROM PHONE 
            WHERE SSN = %s
            """
            cursor.execute(get_phones_query, (self.current_user_ssn,))
            phones = cursor.fetchall()

            if not phones:
                print("No phone numbers found.")
                return

            print("Your phone numbers:")
            for i, (phone, is_primary) in enumerate(phones, 1):
                primary_status = " (Primary)" if is_primary else ""
                print(f"{i}. {phone}{primary_status}")

            choice = input("Enter the number of the phone to remove (or press Enter to cancel): ")
            
            if not choice:
                return

            try:
                phone_index = int(choice) - 1
                phone_to_remove = phones[phone_index][0]
                is_primary = phones[phone_index][1]

                if is_primary:
                    print("Cannot remove primary phone number.")
                    return

                # Remove phone number
                remove_phone_query = """
                DELETE FROM PHONE 
                WHERE SSN = %s AND PhoneNumber = %s
                """
                cursor.execute(remove_phone_query, (self.current_user_ssn, phone_to_remove))
                conn.commit()
                print(f"Phone number {phone_to_remove} removed successfully.")

            except (ValueError, IndexError):
                print("Invalid selection.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to remove phone number:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def add_bank_account(self):
        """Add a new bank account"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        bank_name = input("Enter bank name: ")
        account_number = input("Enter bank account number: ")
        routing_number = input("Enter routing number: ")
        account_type = input("Enter account type ([C] Checking / [S] Savings): ")

        # Generate a bank account id

        # Convert bank name to uppercase and take first 3-4 characters
        bank_prefix = ''.join(word[:1] for word in bank_name.upper().split())[:4]

        bank_account_id = bank_prefix + datetime.now().strftime('%Y%m%d%H%M%S')

        # Basic validation
        if not bank_name or not account_number or not routing_number:
            print("All fields are required.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            account_type_fin = account_type == 'C' if 'CHECKING' else 'SAVINGS' 

            insert_bank_query = """
            INSERT INTO BANK_ACCOUNT 
            (BankID, BANUmber, WalletAccountSSN, Bank_Name, Account_Type, RoutingNumber, Is_Primary, Verified) 
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(insert_bank_query, (
                bank_account_id, account_number, self.current_user_ssn, bank_name, account_type_fin,
                routing_number, False, False
            ))
            conn.commit()
            print("Bank account added successfully.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to add bank account:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

    def remove_bank_account(self):
        """Remove a bank account"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Retrieve user's bank accounts
            get_bank_query = """
            SELECT Bank_Name, BANUmber, Is_Primary 
            FROM BANK_ACCOUNT 
            WHERE WalletAccountSSN = %s
            """
            cursor.execute(get_bank_query, (self.current_user_ssn,))
            bank_accounts = cursor.fetchall()

            if not bank_accounts:
                print("No bank accounts found.")
                return

            print("Your bank accounts:")
            for i, (bank_name, account_number, is_primary) in enumerate(bank_accounts, 1):
                primary_status = " (Primary)" if is_primary else ""
                print(f"{i}. {bank_name} - {account_number}{primary_status}")

            choice = input("Enter the number of the bank account to remove (or press Enter to cancel): ")
            
            if not choice:
                return

            try:
                bank_index = int(choice) - 1
                bank_name = bank_accounts[bank_index][0]
                account_number = bank_accounts[bank_index][1]
                is_primary = bank_accounts[bank_index][2]

                if is_primary:
                    print("Cannot remove primary bank account.")
                    return

                # Remove bank account
                remove_bank_query = """
                DELETE FROM BANK_ACCOUNT 
                WHERE WalletAccountSSN = %s AND Bank_Name = %s AND BANUmber = %s
                """
                cursor.execute(remove_bank_query, (self.current_user_ssn, bank_name, account_number))
                conn.commit()
                print(f"Bank account {bank_name} - {account_number} removed successfully.")

            except (ValueError, IndexError):
                print("Invalid selection.")

        except psycopg2.Error as e:
            conn.rollback()
            print("Failed to remove bank account:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()
    def get_account_info(self):
        """Retrieve and display comprehensive account information"""
        if not self.current_user_ssn:
            print("Please log in first.")
            return

        try:
            conn = self.connect_db()
            cursor = conn.cursor()

            # Retrieve main account details
            account_query = """
            SELECT Name, Email, Phone, Balance 
            FROM WALLET_ACCOUNT 
            WHERE SSN = %s
            """
            cursor.execute(account_query, (self.current_user_ssn,))
            account_info = cursor.fetchone()

            if not account_info:
                print("Account information not found.")
                return

            name, email, phone, balance = account_info

            # Retrieve additional email addresses
            emails_query = """
            SELECT EmailAddress, Is_Primary, Verified 
            FROM EMAIL_ADDRESS 
            WHERE SSN = %s
            """
            cursor.execute(emails_query, (self.current_user_ssn,))
            email_addresses = cursor.fetchall()

            # Retrieve additional phone numbers
            phones_query = """
            SELECT PhoneNumber, Is_Primary, Verified 
            FROM PHONE 
            WHERE SSN = %s
            """
            cursor.execute(phones_query, (self.current_user_ssn,))
            phone_numbers = cursor.fetchall()

            # Retrieve bank accounts
            bank_query = """
            SELECT Bank_Name, BANUmber, Is_Primary, Verified 
            FROM BANK_ACCOUNT 
            WHERE WalletAccountSSN = %s
            """
            cursor.execute(bank_query, (self.current_user_ssn,))
            bank_accounts = cursor.fetchall()

            # Retrieve recent transactions
            recent_transactions_query = """
            (SELECT Recipient_SSN as Other_Party, Amount, 'SENT' as Type, Date_Time_Initiated 
            FROM SEND_TRANSACTION 
            WHERE Sender_SSN = %s)
            UNION
            (SELECT Sender_SSN as Other_Party, Amount, 'RECEIVED' as Type, Date_Time_Initiated 
            FROM SEND_TRANSACTION 
            WHERE Recipient_SSN = %s)
            ORDER BY Date_Time_Initiated DESC
            LIMIT 5
            """
            cursor.execute(recent_transactions_query, (self.current_user_ssn, self.current_user_ssn))
            recent_transactions = cursor.fetchall()

            # Display account information
            print("\n--- Account Information ---")
            print(f"Name: {name}")
            print(f"SSN: {self.current_user_ssn}")
            print(f"Current Balance: ${balance:.2f}")
            
            # Email Addresses
            print("\nEmail Addresses:")
            for email_addr, is_primary, verified in email_addresses:
                status = "Primary" if is_primary else "Secondary"
                verification = "Verified" if verified else "Unverified"
                print(f"- {email_addr} ({status}, {verification})")
            
            # Phone Numbers
            print("\nPhone Numbers:")
            for phone_num, is_primary, verified in phone_numbers:
                status = "Primary" if is_primary else "Secondary"
                verification = "Verified" if verified else "Unverified"
                print(f"- {phone_num} ({status}, {verification})")
            
            # Bank Accounts
            print("\nBank Accounts:")
            for bank_name, account_number, is_primary, verified in bank_accounts:
                status = "Primary" if is_primary else "Secondary"
                verification = "Verified" if verified else "Unverified"
                print(f"- {bank_name} ({account_number}) ({status}, {verification})")
            
            # Recent Transactions
            print("\nRecent Transactions:")
            if recent_transactions:
                for other_party, amount, trans_type, date in recent_transactions:
                    print(f"- {trans_type}: ${amount:.2f} on {date}")
            else:
                print("No recent transactions")

        except psycopg2.Error as e:
            print("Failed to retrieve account information:", e)
        finally:
            if conn:
                cursor.close()
                conn.close()

def main():
    wallet_app = WalletPaymentNetwork()
    
    while True:
        print("\n--- WALLET Payment Network ---")
        print("1. Login")
        print("2. Register")
        print("3. Exit")
        
        choice = input("Enter your choice: ")
        
        if choice == '1':
            if wallet_app.login():
                # Main menu after login
                while True:
                    print("\n--- Main Menu ---")
                    print("1. Account Info")
                    print("2. Send Money")
                    print("3. Request Money")
                    print("4. Statements")
                    print("5. Account Management")
                    print("6. Payment Methods")
                    print("7. Sign Out")
                    
                    menu_choice = input("Enter your choice: ")
                    
                    if menu_choice == '1':
                        wallet_app.get_account_info()
                    elif menu_choice == '2':
                        wallet_app.send_money()
                    elif menu_choice == '3':
                        wallet_app.request_money()
                    elif menu_choice == '4':
                        wallet_app.view_statements()
                    elif menu_choice == '5':
                        wallet_app.manage_account()
                    elif menu_choice == '6':
                        wallet_app.current_user_ssn = None
                        break
                    else:
                        print("Invalid choice. Try again.")
        
        elif choice == '2':
            wallet_app.register_account()
        
        elif choice == '3':
            print("Thank you for using WALLET Payment Network!")
            break
        
        else:
            print("Invalid choice. Try again.")

if __name__ == "__main__":
    main()