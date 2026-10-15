import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

def send_email_alert(subject: str, body_markdown: str):
    """지식 리포트 완성 시 내 이메일로 핵심 요약 알림을 발송합니다."""
    if not GMAIL_USER or not GMAIL_APP_PASSWORD:
        print("  [알림 건너뜀] .env에 GMAIL_USER 또는 GMAIL_APP_PASSWORD가 설정되지 않았습니다.")
        return False
        
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"[Second Brain OS] {subject}"
        msg["From"] = GMAIL_USER
        msg["To"] = GMAIL_USER  # 나에게 발송

        html_content = f"""
        <html>
          <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #222; max-width: 650px; margin: 0 auto; padding: 20px;">
            <div style="background-color: #0e1117; color: #ffffff; padding: 16px 20px; border-radius: 8px 8px 0 0;">
              <h2 style="margin: 0; font-size: 18px;">🧠 Second Brain OS 자율 브리핑</h2>
            </div>
            <div style="border: 1px solid #e1e4e8; border-top: none; padding: 20px; border-radius: 0 0 8px 8px; background-color: #fafbfc;">
              <h3 style="margin-top: 0; color: #0366d6;">📄 {subject}</h3>
              <div style="background-color: #ffffff; padding: 15px; border-radius: 6px; border-left: 4px solid #28a745; margin-bottom: 20px; white-space: pre-wrap;">
{body_markdown}
              </div>
              <p style="font-size: 12px; color: #6a737d; margin: 0;">
                이 메일은 Second Brain 백그라운드 레이더에 의해 자율 생성되어 자동 발송되었습니다.
              </p>
            </div>
          </body>
        </html>
        """
        part = MIMEText(html_content, "html", "utf-8")
        msg.attach(part)

        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, [GMAIL_USER], msg.as_string())
            
        print(f"  ★ [모바일 알림 성공] 이메일({GMAIL_USER})로 브리핑 발송 완료!")
        return True
    except Exception as e:
        print(f"  ! 이메일 발송 실패: {e}")
        return False

if __name__ == "__main__":
    test_subject = "미국 기준금리 경기침체 다각도 교차 검증"
    test_body = "핵심 통찰: 시장의 금리 인하 기대감과 실질 유동성 사이클 간의 3개월 시차(Time-lag) 확인."
    send_email_alert(test_subject, test_body)