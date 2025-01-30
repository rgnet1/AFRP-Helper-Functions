import smtplib
import sys
import os
from typing import Optional

class SMSSender:
    # Define carrier email suffixes as class attributes
    ATT = "@mms.att.net"
    TMOBILE = "@tmomail.net"
    VERIZON = "@vtext.com"
    SPRINT = "@messaging.sprintpcs.com"

    _CARRIERS = {
        "att": ATT,
        "tmobile": TMOBILE,
        "verizon": VERIZON,
        "sprint": SPRINT
    }

    def __init__(self, email: Optional[str] = None, password: Optional[str] = None):
        """Initialize SMSSender with either provided credentials or environment variables.
        
        Args:
            email: Optional email address. If not provided, uses EMAIL env var
            password: Optional password. If not provided, uses EMAIL_APP_PASSWORD env var
        """
        self.email = email or os.getenv("EMAIL")
        self.password = password or os.getenv("EMAIL_APP_PASSWORD")
        
        if not self.email or not self.password:
            raise ValueError("Email and password must be provided either directly or through environment variables")

    def send_message(self, phone_number: str, carrier_email: str, message: str) -> None:
        """Sends an SMS message via email-to-SMS gateway.

        Args:
            phone_number: The recipient's phone number
            carrier_email: The carrier's email suffix
            message: The message to be sent
        """
        recipient = f"{phone_number}{carrier_email}"
        auth = (self.email, self.password)

        try:
            server = smtplib.SMTP("smtp.gmail.com", 587)
            server.starttls()
            server.login(auth[0], auth[1])
            server.sendmail(auth[0], recipient, message)
            server.quit()
            print(f"Message sent to {phone_number} via {carrier_email}.")
        except Exception as e:
            print(f"Failed to send message: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print(f"Usage: python3 {sys.argv[0]} <EMAIL> <PASSWORD> <PHONE_NUMBER> <CARRIER> <MESSAGE>")
        sys.exit(0)

    email = sys.argv[1]
    password = sys.argv[2]
    phone_number = sys.argv[3]
    carrier = sys.argv[4].lower()
    message = sys.argv[5]

    sms_sender = SMSSender(email, password)
    
    # Map the carrier string to the correct attribute
    carrier_email = getattr(SMSSender, carrier.upper(), None)
    
    if carrier_email is None:
        print(f"Carrier '{carrier}' is not supported.")
        sys.exit(1)

    sms_sender.send_message(phone_number, carrier_email, message)
