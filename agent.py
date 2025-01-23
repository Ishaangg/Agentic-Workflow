from langchain.agents import initialize_agent, Tool
from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
import requests
from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import ast, json

load_dotenv()
import os

from langchain.tools import tool
os.environ["LANGCHAIN_TRACING_V2"] = "true"
os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
os.environ["LANGCHAIN_PROJECT"] = "Joblo"

def coerce_to_valid_json(input_str: str) -> str:
    """
    Attempts to convert a Python dict-like string into valid JSON by:
    1) Using ast.literal_eval to parse single-quoted or Pythonic data.
    2) Dumping the result as properly formatted JSON (with double quotes).
    If parsing fails, returns the original string.
    """
    try:
        # Convert from Python-like string (which might have single quotes) to a Python object
        python_obj = ast.literal_eval(input_str)
        # Convert back to strictly valid JSON with double quotes
        return json.dumps(python_obj)
    except:
        # If it fails, just return the original string unmodified
        return input_str

@tool
def calculator(expression: str) -> str:
    """ Evaluate a math expression """
    try:
        result = eval(expression)
        return str(result)
    except Exception as e:
        return f"Error:{e}"

@tool
def web_search(query: str) -> str:
    """Performs a web Search using a google CSE API"""

    try:
        google_api_key = os.getenv("GOOGLE_API_KEY")
        google_cx = os.getenv("GOOGLE_CSE_CX")

        if not google_api_key or not google_cx:
            return "Google CSE API key or CX ID is missing"
        endpoint = "https://www.googleapis.com/customsearch/v1"

        params= {
            "key": google_api_key,
            "cx": google_cx,
            "q": query,
            "dateRestrict": "m6"
        }
        response = requests.get(endpoint, params=params)

        if response.status_code == 200:
            data = response.json()
            if "items" in data and data["items"]:
                top_result = data["items"][0]
                title = top_result.get("title", "No title available")
                snippet = top_result.get("snippet", "No snippet available")
                link = top_result.get("link", "No link available")
                return f"Title: {title}\nSnippet: {snippet}\nLink: {link}"
            else:
                return "No search results found."
        else:
            return f"Error: Unable to fetch search results. Status Code: {response.status_code}"
    except Exception as e:
        return f"Error: {e}"

@tool
def gmail_get_emails(query: str) -> str:
    """
    Retrieves up to 5 recent emails from Gmail using OAuth credentials in .env.

    Usage:
        Provide a search query (Gmail syntax).
        For example: "label:unread" or "subject:Invoice" or just "" (empty) for all mail.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            return "Missing one or more Gmail OAuth credentials in environment variables!"

        creds = Credentials.from_authorized_user_info(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )

        service = build("gmail", "v1", credentials=creds)

        response = (
            service.users()
            .messages()
            .list(userId="me", q=query, maxResults=5)
            .execute()
        )
        messages = response.get("messages", [])
        if not messages:
            return "No emails found for the given query."

        email_summaries = []
        for msg in messages:
            msg_id = msg["id"]
            msg_data = service.users().messages().get(userId="me", id=msg_id).execute()

            snippet = msg_data.get("snippet", "")
            headers = msg_data.get("payload", {}).get("headers", [])
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"), "No Subject"
            )
            from_ = next(
                (h["value"] for h in headers if h["name"] == "From"), "Unknown Sender"
            )

            email_summaries.append(
                f"From: {from_}\nSubject: {subject}\nSnippet: {snippet}\n"
            )

        return "\n".join(email_summaries)

    except Exception as e:
        return f"Error: {e}"
    
@tool
def gmail_send_email(input_data: str) -> str:
    """
    Sends an email using Gmail API with the given input data.

    Input:
    - A JSON string containing 'to', 'subject', and 'body' fields.
      Example:
      {
          "to": "recipient@example.com",
          "subject": "Meeting Reminder",
          "body": "Don't forget about the meeting at 10 AM tomorrow."
      }

    Returns:
    - Success message with sent message ID or error message.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("GMAIL_REFRESH_TOKEN")

        if not all([client_id, client_secret, refresh_token]):
            return "Missing one or more Gmail OAuth credentials in environment variables!"

        # Parse input data
        input_data = coerce_to_valid_json(input_data)
        input_json = json.loads(input_data)
        to = input_json.get("to")
        subject = input_json.get("subject")
        body = input_json.get("body")

        if not to or not subject or not body:
            return "Invalid input data! Ensure 'to', 'subject', and 'body' fields are provided."

        creds = Credentials.from_authorized_user_info(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )

        service = build("gmail", "v1", credentials=creds)

        # Create the email
        from email.mime.text import MIMEText
        import base64

        message = MIMEText(body)
        message["to"] = to
        message["subject"] = subject

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        message_body = {"raw": raw_message}

        # Send the email
        sent_message = (
            service.users().messages().send(userId="me", body=message_body).execute()
        )
        return f"Email sent successfully! Message ID: {sent_message['id']}"

    except Exception as e:
        return f"Error: {e}"


@tool
def google_calendar_list_events(query: str) -> str:
    """
    Lists the next 5 upcoming events from Google Calendar using OAuth credentials.
    Requires GOOGLE_CLIENT_ID, GMAIL_CLIENT_SECRET, and GMAIL_REFRESH_TOKEN in .env.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("CALENDAR_REFRESH_TOKEN")

        if not (client_id and client_secret and refresh_token):
            return "Missing Google Calendar OAuth credentials in environment variables!"

        creds = Credentials.from_authorized_user_info(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )

        service = build("calendar", "v3", credentials=creds)

        events_result = service.events().list(
            calendarId="primary", maxResults=5, singleEvents=True, orderBy="startTime"
        ).execute()

        events = events_result.get("items", [])
        if not events:
            return "No upcoming events found."

        output = []
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "No Title")
            output.append(f"{start} - {summary}")

        return "\n".join(output)

    except Exception as e:
        return f"Error: {e}"

@tool
def google_calendar_create_event(input_data: str) -> str:
    """
    Creates a new event in Google Calendar using the provided input data.

    Input:
    - A JSON string containing event details such as 'summary', 'location', 'description',
      'start', and 'end'. The 'start' and 'end' should include 'dateTime' and 'timeZone'.

      Example:
      {
          "summary": "Project Meeting",
          "location": "Conference Room",
          "description": "Discussing project milestones and deadlines.",
          "start": {
              "dateTime": "2025-02-01T10:00:00",
              "timeZone": "UST"
          },
          "end": {
              "dateTime": "2025-02-01T11:00:00",
              "timeZone": "UST"
          }
      }

    Returns:
    - Success message with event ID or detailed error message.
    """
    try:
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        refresh_token = os.getenv("CALENDAR_REFRESH_TOKEN")

        if not (client_id and client_secret and refresh_token):
            return "Missing Google Calendar OAuth credentials in environment variables!"

        # Parse input data
        event_data = json.loads(input_data)

        # Validate required fields
        required_fields = ['summary', 'start', 'end']
        for field in required_fields:
            if field not in event_data:
                return f"Missing required field: {field}"

        creds = Credentials.from_authorized_user_info(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "refresh_token": refresh_token,
                "token_uri": "https://oauth2.googleapis.com/token",
            }
        )

        service = build("calendar", "v3", credentials=creds)

        event = {
            'summary': event_data['summary'],
            'location': event_data.get('location', ''),
            'description': event_data.get('description', ''),
            'start': event_data['start'],
            'end': event_data['end'],
            'reminders': {
                'useDefault': True,
            },
        }

        created_event = service.events().insert(calendarId='primary', body=event).execute()

        if isinstance(created_event, dict) and 'id' in created_event:
            return f"Event created successfully! Event ID: {created_event.get('id')}"
        else:
            # If the API returns an error message as a string
            return f"Error: Unexpected response format. Response: {created_event}"

    except Exception as e:
        return f"Error: {e}"

# Initialize OpenAI LLM
api_key = os.getenv("OPENAI_API_KEY")
llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0)

# Define the list of tools including the new calendar creation tool
tools = [
    Tool(name="Calculator", func=calculator, description="Performs calculations"),
    Tool(name="webSearch", func=web_search, description="Searches the web for a query using Google Custom Search."),
    Tool(name="gmailGetEmails", func=gmail_get_emails, description="Retrieves up to 5 recent emails from Gmail based on a search query."),
    Tool(name="GoogleCalendarListEvents", func=google_calendar_list_events, description="Lists upcoming Google Calendar events."),
    Tool(name="googleCalendarCreateEvent", func=google_calendar_create_event, description="Creates a new event in Google Calendar with provided details."),
    Tool(name="gmailSendEmail", func=gmail_send_email, description="Sends an email using Gmail API."),
]

# Initialize the agent with the updated tools list
agent = initialize_agent(tools, llm, agent="zero-shot-react-description", verbose=True)

response = agent.run(f"Web search and tell me something about Rajat Dalal")
print(response)
