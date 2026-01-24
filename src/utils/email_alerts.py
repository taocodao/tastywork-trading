"""
Email Alert Utility for Position Monitoring.

Sends email notifications when exit signals trigger.
"""

import os
import logging
from typing import Optional, List
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

logger = logging.getLogger(__name__)


class EmailAlertService:
    """Service for sending email alerts about positions."""
    
    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: Optional[int] = None,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        from_email: Optional[str] = None
    ):
        """
        Initialize email service.
        
        Email recipients are determined from Position.user_email (from Privy).
        
        Args:
            smtp_host: SMTP server hostname (default: from env SMTP_HOST)
            smtp_port: SMTP port (default: from env SMTP_PORT or 587)
            smtp_user: SMTP username (default: from env SMTP_USER)
            smtp_password: SMTP password (default: from env SMTP_PASSWORD)
            from_email: Sender email (default: from env FROM_EMAIL)
        """
        self.smtp_host = smtp_host or os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = smtp_port or int(os.getenv('SMTP_PORT', '587'))
        self.smtp_user = smtp_user or os.getenv('SMTP_USER')
        self.smtp_password = smtp_password or os.getenv('SMTP_PASSWORD')
        self.from_email = from_email or os.getenv('FROM_EMAIL', self.smtp_user)
        
        # Validate configuration
        if not self.smtp_user or not self.smtp_password:
            logger.warning("Email alerts not configured. Set SMTP_USER and SMTP_PASSWORD env vars.")
            self.enabled = False
        else:
            self.enabled = True
            logger.info(f"Email alerts enabled. Sender: {self.from_email}")
    
    def send_exit_alert(
        self,
        user_email: str,
        position_id: str,
        symbol: str,
        exit_rule: str,
        exit_reason: str,
        current_value: float,
        entry_debit: float,
        pnl_percent: float,
        unrealized_pnl: float
    ) -> bool:
        """
        Send an exit alert email to the user.
        
        Args:
            user_email: User's email address (from Privy)
            position_id: Position ID
            symbol: Underlying symbol
            exit_rule: Which rule triggered
            exit_reason: Detailed reason
            current_value: Current spread value
            entry_debit: Original entry debit
            pnl_percent: Profit/loss percentage
            unrealized_pnl: Unrealized P&L in dollars
            
        Returns:
            True if sent successfully
        """
        if not self.enabled:
            return False
        
        if not user_email:
            logger.warning(f"No user email available for position {position_id}")
            return False
            
        try:
            # Build email
            subject = f"🚨 EXIT ALERT: {symbol} Calendar Spread - {exit_rule}"
            
            # HTML body
            html_body = f"""
            <html>
            <body style="font-family: Arial, sans-serif; padding: 20px;">
                <h2 style="color: #d32f2f;">🚨 Calendar Spread Exit Alert</h2>
                
                <div style="background-color: #f5f5f5; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <p><strong>Symbol:</strong> {symbol}</p>
                    <p><strong>Position ID:</strong> {position_id}</p>
                    <p><strong>Exit Rule Triggered:</strong> {exit_rule}</p>
                    <p><strong>Reason:</strong> {exit_reason}</p>
                </div>
                
                <div style="background-color: #e3f2fd; padding: 15px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="margin-top: 0;">Position Details</h3>
                    <p><strong>Entry Debit:</strong> ${entry_debit:.2f}</p>
                    <p><strong>Current Value:</strong> ${current_value:.2f}</p>
                    <p><strong>Unrealized P&L:</strong> <span style="color: {'#4caf50' if unrealized_pnl >= 0 else '#d32f2f'}; font-weight: bold;">${unrealized_pnl:.2f} ({pnl_percent:+.1f}%)</span></p>
                </div>
                
                <div style="margin: 20px 0;">
                    <p><strong>Recommended Action:</strong> Review this position and consider closing it via the dashboard.</p>
                </div>
                
                <p style="color: #666; font-size: 12px; margin-top: 30px;">
                    Alert generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
                </p>
            </body>
            </html>
            """
            
            # Plain text fallback
            text_body = f"""
EXIT ALERT: {symbol} Calendar Spread

Exit Rule Triggered: {exit_rule}
Reason: {exit_reason}

Position Details:
- Position ID: {position_id}
- Entry Debit: ${entry_debit:.2f}
- Current Value: ${current_value:.2f}
- Unrealized P&L: ${unrealized_pnl:.2f} ({pnl_percent:+.1f}%)

Recommended Action: Review this position and consider closing it.

Alert generated at {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
            """
            
            # Create message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            msg['To'] = user_email
            
            # Attach both versions
            msg.attach(MIMEText(text_body, 'plain'))
            msg.attach(MIMEText(html_body, 'html'))
            
            # Send
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info(f"Exit alert email sent for {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send exit alert email: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def send_test_alert(self, test_email: Optional[str] = None) -> bool:
        """Send a test email to verify configuration.
        
        Args:
            test_email: Optional email to send test to (defaults to SMTP_USER)
        """
        if not self.enabled:
            logger.error("Email alerts not enabled")
            return False
        
        recipient = test_email or self.smtp_user
        if not recipient:
            logger.error("No test email recipient specified")
            return False
            
        try:
            msg = MIMEText("This is a test alert from TradeMind Position Monitor.")
            msg['Subject'] = "Test Alert - TradeMind Position Monitor"
            msg['From'] = self.from_email
            msg['To'] = recipient
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            logger.info("Test email sent successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send test email: {e}")
            return False
