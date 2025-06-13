# Create a slack bot that can suggest people for QA in a team
# import os
# import slack_sdk
# from slack_sdk import WebClient
# from slack_sdk.errors import SlackApiError
# from slack_sdk.web import SlackResponse
# from slack_sdk.webhook import WebhookClient
# from slack_sdk.models.blocks import SectionBlock, ActionsBlock, ButtonElement
# from slack_sdk.models.attachments import Attachment
# from slack_sdk.models import Message
# from slack_sdk.web.slack_response import SlackResponse
# from slack_sdk.webhook import WebhookResponse
# from slack_sdk.webhook import WebhookClient
# from slack_sdk.web import SlackResponse
# from slack_sdk.models.blocks import Block
# from slack_sdk.models.blocks import SectionBlock, ActionsBlock, ButtonElement
# from slack_sdk.web import WebClient
# from slack_sdk.errors import SlackApiError
# # Initialize the Slack client
# slack_token = os.environ.get("SLACK_BOT_TOKEN")
# if not slack_token:
#     raise ValueError("SLACK_BOT_TOKEN environment variable is not set.")
# client = WebClient(token=slack_token)

import os
import json
import requests
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
import ssl
import certifi
import urllib.request
import openai
from urllib.parse import urlparse

ssl_context = ssl.create_default_context(cafile=certifi.where())
urllib.request.urlopen("https://slack.com", context=ssl_context)

# Load environment variables from .env file
load_dotenv()
# Initialize the Slack app
app = App(token=os.getenv("SLACK_BOT_TOKEN"), signing_secret=os.getenv("SLACK_SIGNING_SECRET"))
client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

bb_username = os.getenv("BB_USERNAME")
bb_app_password = os.getenv("BB_APP_PASSWORD")

# Load QA mapping
with open("QA_map.json") as f:
    qa_map = json.load(f)

# Jira ticket fetch
def get_jira_ticket(ticket_id):
    """
    Fetches a Jira ticket by its ID.
    Args:
        ticket_id (str): The ID of the Jira ticket to fetch.
    Returns:
        dict: The Jira ticket data if found, None otherwise.
    """
    if not ticket_id:
        return None
    baseUrl = os.getenv("JIRA_BASE_URL")
    print(f"Jira base URL: {baseUrl}")
    url = f"{baseUrl}/rest/api/3/issue/{ticket_id}"
    auth = (os.getenv("JIRA_EMAIL"), os.getenv("JIRA_API_TOKEN"))
    headers = {"Accept": "application/json"}
    response = requests.get(url, headers=headers, auth=auth)
    # print(f"Fetching Jira ticket {ticket_id} from {url}")
    # print(f"Response status code: {response.json() if response.status_code == 200 else response.status_code}")
    return response.json() if response.status_code == 200 else None

ticket = get_jira_ticket("FRA-36519")

def parse_ticket_info(ticket):
    with open("some.json", "w", encoding="utf-8") as f:
        json.dump(ticket, f, indent=2, ensure_ascii=False)
    print(f"Ticket saved to {"some.json"}")
    fields = ticket.get("fields", {})
    assignee = (fields.get("assignee") or {}).get("displayName", "Not Assigned")
    reporter = (fields.get("reporter") or {}).get("displayName", "Not Assigned")
    labels = fields.get("labels") or []
    status = (fields.get("status") or {}).get("name", "Unknown")
    description = fields.get("description", {}).get("content", [])
    print(f"Description: {description[0]['content'][0]['attrs']['url']}")

    # Dev assignee = same as assignee (unless custom field exists)
    dev_assignee = assignee

    # Parent ticket info
    parent = fields.get("parent", {})
    parent_key = parent.get("key", "None")
    parent_summary = parent.get("fields", {}).get("summary", "No summary") if parent else "N/A"

    # Bitbucket PR info (customfield_13300)
    pr_info_raw = fields.get("customfield_13300", "")
    pr_info = "None"
    if isinstance(pr_info_raw, str):
        try:
            pr_info_json = json.loads(pr_info_raw)
            pr_info = pr_info_json.get("cachedValue", {}).get("summary", {}).get("pullrequest", {}).get("overall", {})
        except Exception:
            pr_info = pr_info_raw

    print("---- Ticket Summary ----")
    print(f"🎫 Ticket: {ticket.get('key')}")
    print(f"👤 Assignee: {assignee}")
    print(f"📝 Reporter: {reporter}")
    print(f"👨‍💻 Dev Assignee: {dev_assignee}")
    print(f"🏷️ Labels: {', '.join(labels) if labels else 'None'}")
    print(f"📌 Status: {status}")
    print(f"📂 Parent: {parent_key} - {parent_summary}")
    print(f"🔗 PR Info: {pr_info}")

parse_ticket_info(ticket)

@app.command("/gpt")
def handle_gpt_command(ack, respond, command):
    ack()
    prompt = command.get("text", "").strip()
    if not prompt:
        respond("❗ Please provide a prompt or question. Example: `/gpt How do I write unit tests?`")
        return
    try:
        completion = client.chat.completions.create(
            model="gpt-3.5-turbo",  # Or "gpt-3.5-turbo"
            messages=[
                {"role": "system", "content": "You are a helpful AI assistant for the Fetch Rewards QA and developer team."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7
        )
        answer = completion.choices[0].message.content.strip()
        respond(f"💡 *GPT says:*\n{answer}")
    except Exception as e:
        print("OpenAI API error:", e)
        respond("⚠️ There was an error contacting ChatGPT. Please try again later.")

@app.command("/ticket")
def handle_ticket_command(ack, respond, command):
    print("✅ Received /ticket command")
    try:
        ack()
        print(command)
        ticket_id = command["text"].strip()
        if not ticket_id:
            respond("Please provide a Jira ticket ID.")
            return
        ticket = get_jira_ticket(ticket_id)
        if not ticket:
            respond(f"Ticket {ticket_id} not found.")
            return

        fields = ticket.get("fields", {})
        assignee = (fields.get("assignee") or {}).get("displayName", "Not Assigned")
        reporter = (fields.get("reporter") or {}).get("displayName", "Not Assigned")
        labels = fields.get("labels") or []
        status = (fields.get("status") or {}).get("name", "Unknown")

        response_text = (
            f"🎫 Ticket: {ticket.get('key')}\n"
            f"👤 Assignee: {assignee}\n"
            f"📝 Reporter: {reporter}\n"
            f"🏷️ Labels: {', '.join(labels) if labels else 'None'}\n"
            f"📌 Status: {status}\n"
            f"🔗 View Ticket: {os.getenv('JIRA_BASE_URL')}/browse/{ticket.get('key')}\n"
        )
        respond(response_text)

    except Exception as e:
        print(f"Error handling slash command: {e}")
        respond("Something went wrong while fetching the ticket.")

@app.command("/list-teams")
def list_teams_command(ack, respond):
    ack()
    try:
        # Get only top 5 QA-related channels
        channels = []
        cursor = None
        while True:
            result = app.client.conversations_list(
                types="public_channel,private_channel",
                limit=5,
                cursor=cursor
            )
            channels.extend(result.get("channels", []))
            cursor = result.get("response_metadata", {}).get("next_cursor")
            if not cursor:
                break

        # Only process the first 5 QA channels
        qa_channels = [ch for ch in channels if 'qa' in ch["name"]][:3]
        if not qa_channels:
            respond("No QA channels found!")
            return

        response_lines = ["*Top QA Channels & Members:*"]
        for ch in qa_channels:
            channel_name = ch["name"]
            channel_id = ch["id"]

            # Step 3: Get members in channel (limit to 10 users)
            members = []
            mem_cursor = None
            while True:
                mem_result = app.client.conversations_members(channel=channel_id, limit=10, cursor=mem_cursor)
                members.extend(mem_result.get("members", []))
                mem_cursor = mem_result.get("response_metadata", {}).get("next_cursor")
                if not mem_cursor or len(members) >= 10:
                    break
            members = members[:5]  # show only top 10 users

            # Step 4: Fetch user details for each member
            user_details = []
            for user_id in members:
                user_info = app.client.users_info(user=user_id)
                if user_info.get("ok"):
                    profile = user_info["user"]["profile"]
                    real_name = profile.get("real_name", "Unknown")
                    display_name = profile.get("display_name", "Unknown")
                    title = profile.get("title", "")
                    user_details.append(
                        f"<@{user_id}> (`{display_name}` / {real_name}{' - ' + title if title else ''})"
                    )

            users_line = ", ".join(user_details) if user_details else "_No members found_"
            response_lines.append(f"\n*#{channel_name}*:\n{users_line}")

        response_text = "\n".join(response_lines)
        respond(response_text)

    except Exception as e:
        print("Error in /list-teams:", e)
        respond("Something went wrong while listing teams.")


@app.command("/suggest-qa2")
def suggest_qa_command(ack, respond, command):
    ack()
    ticket_id = command.get("text", "").strip()
    if not ticket_id:
        respond("Please provide a Jira ticket ID. Example: `/suggest-qa FET-1234`")
        return

    ticket = get_jira_ticket(ticket_id)
    if not ticket:
        respond(f"Ticket `{ticket_id}` not found.")
        return

    fields = ticket.get("fields", {})
    labels = [label.lower() for label in fields.get("labels", [])]

    # Map known label → QA channel (customize as needed)
    label_to_channel = {
        "android-guild": "guild-qa",
        "lakitu": "pack-lakitu-qa",
        "android": "guild-qa",
        "elluminati": "collective-ereceipt-qa"
    }

    channel_to_id = {
        "pack-lakitu-qa": "C08JXA5PS00",  # Example channel ID, replace with actual
        "guild-qa": "CKGFVBNTZ",  # Example channel ID, replace with actual
        "collective-ereceipt-qa": "C01XYZ4567QW",  # Example channel ID, replace with actual
        'pack-felix-qa': 'C089K8PM44R',  # Example channel ID, replace with actual
    }

    # Find first matching label-channel
    matched_channel = None
    for label in labels:
        if label in label_to_channel:
            matched_channel = label_to_channel[label]
            break
    if not matched_channel:
        matched_channel = "pack-lakitu-qa"  # fallback

    # --- NEW: Paginate through all channels to find the right one(s) ---
    channels = []
    cursor = None
    while True:
        result = app.client.conversations_list(
            types="public_channel,private_channel",
            limit=100,
            cursor=cursor
        )
        channels.extend(result.get("channels", []))
        cursor = result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
    print(f"Found {len(channels)} channels in total.", channels)
    # Only use channels the bot is a member of!
    qa_channels = [ch for ch in channels if "qa" in ch["name"] and ch.get("is_member")]
    print(f"Filtered QA channels: {len(qa_channels)}", qa_channels)
    channel_obj = next((ch for ch in qa_channels if ch["name"] == matched_channel), None)
    if not channel_obj:
        respond(f"Could not find the Slack channel for `{matched_channel}`. (Is the bot invited to that channel?)")
        return
    channel_id = channel_obj["id"]

    # Get all members in the channel
    members = []
    cursor = None
    while True:
        mem_result = app.client.conversations_members(channel=channel_id, limit=100, cursor=cursor)
        members.extend(mem_result.get("members", []))
        cursor = mem_result.get("response_metadata", {}).get("next_cursor")
        if not cursor:
            break
        if len(members) >= 100:
            break

    # Check Slack presence and collect active QAs
    active_qa_mentions = []
    for user_id in members:
        user_info = app.client.users_info(user=user_id)
        profile = user_info["user"]["profile"]
        is_qa = "qa" in (profile.get("title", "") + profile.get("real_name", "") + profile.get("display_name", "")).lower()
        if not is_qa:
            continue
        presence = app.client.users_getPresence(user=user_id)
        if presence.get("presence") == "active":
            active_qa_mentions.append(f"<@{user_id}>")

    if active_qa_mentions:
        respond(
            f"📄 Ticket `{ticket_id}` has label(s) `{', '.join(labels)}`.\n"
            f"👥 *Active QAs in* #{matched_channel}: {', '.join(active_qa_mentions)}"
        )
    else:
        respond(
            f"📄 Ticket `{ticket_id}` has label(s) `{', '.join(labels)}`.\n"
            f"😕 No active QA found in #{matched_channel}. Showing all QAs in that channel:"
        )
        all_qa_mentions = []
        for user_id in members:
            user_info = app.client.users_info(user=user_id)
            profile = user_info["user"]["profile"]
            is_qa = "qa" in (profile.get("title", "") + profile.get("real_name", "") + profile.get("display_name", "")).lower()
            if is_qa:
                all_qa_mentions.append(f"<@{user_id}>")
        respond(f"👥 QAs in #{matched_channel}: {', '.join(all_qa_mentions) if all_qa_mentions else 'None'}")
@app.command("/suggest-qa")
def suggest_qa_command(ack, respond, command):
    ack()
    ticket_id = command.get("text", "").strip()
    if not ticket_id:
        respond("Please provide a Jira ticket ID. Example: `/suggest-qa FET-1234`")
        return

    ticket = get_jira_ticket(ticket_id)
    if not ticket:
        respond(f"Ticket `{ticket_id}` not found.")
        return

    fields = ticket.get("fields", {})
    team_name = (fields.get("customfield_13400") or {}).get("name", "").lower()
    jira_base_url = os.getenv("JIRA_BASE_URL", "").rstrip("/")
    ticket_link = f"{jira_base_url}/browse/{ticket_id}"
    ticket_title = fields.get("summary", "No title found")
    assignee = (fields.get("assignee") or {}).get("displayName", "Not Assigned")
    reporter = (fields.get("reporter") or {}).get("displayName", "Not Assigned")

    team_to_channel = {
        "pack-lakitu": "pack-lakitu-qa",
        "guild-android": "guild-qa",
        "guild-ios": "guild-qa",
        "pack-elluminati": "collective-ereceipt-qa",
        "pack-felix": "pack-felix-qa",
        "pack-midas": "pack-midas-qa",
        "collective rewarded apps": "collective-rewarded-apps-qa",
        "pack-gameplay": "pack-gameplay-qa",
        "pack-kallax": "pack-kallax-qa",
        "apogee": "pack-apogee-qa",
        "famex": "pack-famex-qa",
        "rover": "pack-rover-qa-channel",
    }
    channel_to_id = {
        "pack-lakitu-qa": "C08JXA5PS00",
        "guild-qa": "CKGFVBNTZ",
        "collective-ereceipt-qa": "C04ADQQN97H",
        "pack-felix-qa": "C089K8PM44R",
        "pack-midas-qa": "C077L0N8WHZ",
        "collective-rewarded-apps-qa": "C06GU3KJH08",
        "pack-gameplay-qa": "C066Q2F9HC6",
        "pack-kallax-qa": "C083ZRKV7FA",
        "pack-apogee-qa": "C082W411ZAB",
        "pack-famex-qa": "C07JWD76LCX",
        "pack-rover-qa-channel": "C08D19XDAHX",
    }

    matched_channel = team_to_channel.get(team_name, "pack-lakitu-qa")
    channel_id = channel_to_id.get(matched_channel)
    channel_mention = f"<#{channel_id}|{matched_channel}>" if channel_id else matched_channel

    if not channel_id:
        respond(f"Could not find the channel ID for `{matched_channel}`. Please update the mapping.")
        return

    # Get channel members
    members = []
    cursor = None
    while True:
        mem_result = app.client.conversations_members(channel=channel_id, limit=100, cursor=cursor)
        members.extend(mem_result.get("members", []))
        cursor = mem_result.get("response_metadata", {}).get("next_cursor")
        if not cursor or len(members) >= 100:
            break

    # Split QAs by active/non-active
    active_qa_mentions = []
    inactive_qa_mentions = []
    for user_id in members:
        user_info = app.client.users_info(user=user_id)
        profile = user_info["user"]["profile"]
        is_qa = "qa" in (profile.get("title", "") + profile.get("real_name", "") + profile.get("display_name", "")).lower()
        if not is_qa:
            continue
        presence = app.client.users_getPresence(user=user_id)
        if presence.get("presence") == "active":
            active_qa_mentions.append(f"<@{user_id}>")
        else:
            inactive_qa_mentions.append(f"<@{user_id}>")

    # Format output
    response_lines = [
        f"*Ticket*: <{ticket_link}|`{ticket_id}`>",
        f"*Title*: {ticket_title}",
        f"*Assignee*: {assignee}",
        f"*Reporter*: {reporter}",
        f"*Team*: `{team_name}`",
        f"*Channel*: {channel_mention}",
        "",
    ]
    if active_qa_mentions:
        response_lines.append(f"*Active QAs:* {', '.join(active_qa_mentions)}")
    else:
        response_lines.append("_No active QAs found._")

    if inactive_qa_mentions:
        response_lines.append(f"*Non-active QAs:* {', '.join(inactive_qa_mentions)}")
    else:
        response_lines.append("_No non-active QAs found._")

    if not active_qa_mentions and not inactive_qa_mentions:
        response_lines.append("_No QAs found in this channel._")

    respond("\n".join(response_lines))

# --- Helper: Extract PR link from description ---
def extract_pr_link_from_jira(fields):
    desc = fields.get("description", {})
    print(f"Description content: {desc}")
    # if desc and isinstance(desc, dict):
    #     for block in desc.get("content", []):
    #         if block.get("type") == "paragraph":
    #             for item in block.get("content", []):
    #                 if item.get("type") == "inlineCard" and "url" in item.get("attrs", {}):
    #                     return item["attrs"]["url"]
    if desc['content'][0]['content'][0]['attrs']['url']:
        return desc['content'][0]['content'][0]['attrs']['url']
    # Optionally, try to get from a custom field (if description is missing)
    # If you have another field, add extraction logic here.
    return None

# --- Helper: Parse Bitbucket PR URL ---
def parse_bitbucket_pr_url(pr_url):
    parsed = urlparse(pr_url)
    parts = parsed.path.strip('/').split('/')
    if len(parts) >= 4 and parts[2] == "pull-requests":
        workspace = parts[0]
        repo_slug = parts[1]
        pr_id = parts[3]
        return workspace, repo_slug, pr_id
    return None, None, None

# --- Helper: Get Bitbucket PR details and changed files ---
def get_bitbucket_pr_details(workspace, repo_slug, pr_id, bb_username, bb_app_password):
    pr_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}"
    resp = requests.get(pr_url, auth=(bb_username, bb_app_password))
    pr_data = resp.json() if resp.status_code == 200 else {}

    diffstat_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diffstat"
    diff_resp = requests.get(diffstat_url, auth=(bb_username, bb_app_password))
    files = []
    if diff_resp.status_code == 200:
        for entry in diff_resp.json().get("values", []):
            # 'new' is the post-change file path; fallback to 'old'
            path = (entry.get("new") or entry.get("old") or {}).get("path")
            if path:
                files.append(path)
    return pr_data, files

# --- Helper: Infer module/package from file path (customize this as needed) ---
def infer_module_from_file(filepath):
    # Example: 'android/app/src/...', 'rewards/models.py'
    if filepath.startswith("android/"):
        return "Android"
    elif filepath.startswith("rewards/"):
        return "Rewards"
    elif filepath.startswith("receipts/"):
        return "Receipts"
    else:
        # Return the top-level folder as module name
        return filepath.split("/")[0] if "/" in filepath else "root"

# --- Slack Command: /ticket-pr-details ---
@app.command("/pr-details")
def ticket_pr_details_command(ack, respond, command):
    ack()
    ticket_id = command.get("text", "").strip()
    if not ticket_id:
        respond("Please provide a Jira ticket ID.")
        return

    ticket = get_jira_ticket(ticket_id)
    if not ticket:
        respond(f"Ticket `{ticket_id}` not found.")
        return

    fields = ticket.get("fields", {})

    # --- JIRA ticket summary (from your existing code) ---
    assignee = (fields.get("assignee") or {}).get("displayName", "Not Assigned")
    reporter = (fields.get("reporter") or {}).get("displayName", "Not Assigned")
    labels = fields.get("labels") or []
    status = (fields.get("status") or {}).get("name", "Unknown")

    # --- PR extraction ---
    pr_link = extract_pr_link_from_jira(fields)
    if not pr_link:
        respond(f"No PR link found in the Jira ticket description for `{ticket_id}`.")
        return

    workspace, repo_slug, pr_id = parse_bitbucket_pr_url(pr_link)
    if not workspace:
        respond("Could not parse Bitbucket PR URL.")
        return

    # --- Bitbucket details ---
    pr_data, files = get_bitbucket_pr_details(workspace, repo_slug, pr_id, bb_username, bb_app_password)

    pr_title = pr_data.get("title", "Unknown")
    author = pr_data.get("author", {}).get("display_name", "Unknown")
    created_on = pr_data.get("created_on", "Unknown")
    pr_status = pr_data.get("state", "Unknown")
    pr_web_url = pr_data.get("links", {}).get("html", {}).get("href", pr_link)
    branch_from = pr_data.get("source", {}).get("branch", {}).get("name", "Unknown")
    branch_to = pr_data.get("destination", {}).get("branch", {}).get("name", "Unknown")

    # --- Per-file module inference ---
    modules = set()
    file_lines = []
    for f in files[:15]:  # show up to 15 files
        mod = infer_module_from_file(f)
        modules.add(mod)
        file_lines.append(f"• `{f}` _(module: {mod})_")
    more_files = "\n...and more" if len(files) > 15 else ""
    modules_line = ", ".join(sorted(modules)) if modules else "Unknown"

    # --- Construct response ---
    response = (
        f"*Jira Ticket*: `{ticket_id}` (Project: {project})\n"
        f"*Status*: {status} | *Labels*: {', '.join(labels) if labels else 'None'}\n"
        f"*Assignee*: {assignee} | *Reporter*: {reporter}\n"
        f"\n*PR Title*: {pr_title}\n"
        f"*Author*: {author}\n"
        f"*Created On*: {created_on}\n"
        f"*Status*: {pr_status}\n"
        f"*From Branch*: `{branch_from}` → *To*: `{branch_to}`\n"
        f"*PR Link*: {pr_web_url}\n"
        f"\n*Changed Files* ({len(files)}):\n" +
        "\n".join(file_lines) +
        more_files +
        (f"\n\n*Modules/Packages affected*: {modules_line}" if modules else "")
    )
    respond(response)

def parse_bitbucket_pr_url2(pr_url):
    parsed = urlparse(pr_url)
    parts = parsed.path.strip('/').split('/')
    if len(parts) >= 4 and parts[2] == "pull-requests":
        workspace = parts[0]
        repo_slug = parts[1]
        pr_id = parts[3]
        return workspace, repo_slug, pr_id
    return None, None, None

def get_bitbucket_pr_details2(workspace, repo_slug, pr_id, bb_username, bb_app_password):
    pr_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}"
    resp = requests.get(pr_url, auth=(bb_username, bb_app_password))
    pr_data = resp.json() if resp.status_code == 200 else {}

    diffstat_url = f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}/pullrequests/{pr_id}/diffstat"
    diff_resp = requests.get(diffstat_url, auth=(bb_username, bb_app_password))
    files = []
    if diff_resp.status_code == 200:
        for entry in diff_resp.json().get("values", []):
            path = (entry.get("new") or entry.get("old") or {}).get("path")
            if path:
                files.append(path)
    return pr_data, files

def infer_module_from_file2(filepath):
    # Simple: use top-level folder, customize for your org as needed
    return filepath.split("/")[0] if "/" in filepath else "root"

@app.command("/pr-inspect")
def pr_inspect_command(ack, respond, command):
    ack()
    pr_link = command.get("text", "").strip()
    if not pr_link or "bitbucket.org" not in pr_link:
        respond("Please provide a Bitbucket PR link. Example: `/pr-inspect https://bitbucket.org/your_workspace/your_repo/pull-requests/12345`")
        return

    workspace, repo_slug, pr_id = parse_bitbucket_pr_url2(pr_link)
    if not workspace:
        respond("Could not parse the Bitbucket PR link.")
        return

    pr_data, files = get_bitbucket_pr_details2(workspace, repo_slug, pr_id, bb_username, bb_app_password)

    pr_title = pr_data.get("title", "Unknown")
    author = pr_data.get("author", {}).get("display_name", "Unknown")
    created_on = pr_data.get("created_on", "Unknown")
    status = pr_data.get("state", "Unknown")
    pr_web_url = pr_data.get("links", {}).get("html", {}).get("href", pr_link)
    branch_from = pr_data.get("source", {}).get("branch", {}).get("name", "Unknown")
    branch_to = pr_data.get("destination", {}).get("branch", {}).get("name", "Unknown")
    reviewers = [r.get("display_name", "Unknown") for r in pr_data.get("reviewers", [])]
    reviewers_line = ", ".join(reviewers) if reviewers else "None"

    # Per-file module inference
    modules = set()
    file_lines = []
    for f in files[:15]:  # show up to 15 files
        mod = infer_module_from_file2(f)
        modules.add(mod)
        file_lines.append(f"• `{f}` _(module: {mod})_")
    more_files = "\n...and more" if len(files) > 15 else ""
    modules_line = ", ".join(sorted(modules)) if modules else "Unknown"

    response = (
        f"*PR Title*: {pr_title}\n"
        f"*Author*: {author}\n"
        f"*Status*: {status}\n"
        f"*From Branch*: `{branch_from}` → *To*: `{branch_to}`\n"
        f"*Reviewers*: {reviewers_line}\n"
        f"*Created On*: {created_on}\n"
        f"*PR Link*: {pr_web_url}\n"
        f"\n*Changed Files* ({len(files)}):\n" +
        "\n".join(file_lines) +
        more_files +
        (f"\n\n*Modules/Packages affected*: {modules_line}" if modules else "")
    )
    respond(response)

@app.command("/suggest-qa-pr")
def suggest_qa_pr_command(ack, respond, command):
    ack()
    pr_link = command.get("text", "").strip()
    if not pr_link or "bitbucket.org" not in pr_link:
        respond("Please provide a Bitbucket PR link. Example: `/suggest-qa-pr https://bitbucket.org/your_workspace/your_repo/pull-requests/12345`")
        return

    workspace, repo_slug, pr_id = parse_bitbucket_pr_url2(pr_link)
    if not workspace:
        respond("Could not parse the Bitbucket PR link.")
        return

    pr_data, files = get_bitbucket_pr_details2(workspace, repo_slug, pr_id, bb_username, bb_app_password)

    pr_title = pr_data.get("title", "Unknown")
    author = pr_data.get("author", {}).get("display_name", "Unknown")
    created_on = pr_data.get("created_on", "Unknown")
    status = pr_data.get("state", "Unknown")
    pr_web_url = pr_data.get("links", {}).get("html", {}).get("href", pr_link)
    branch_from = pr_data.get("source", {}).get("branch", {}).get("name", "Unknown")
    branch_to = pr_data.get("destination", {}).get("branch", {}).get("name", "Unknown")
    reviewers = [r.get("display_name", "Unknown") for r in pr_data.get("reviewers", [])]
    reviewers_line = ", ".join(reviewers) if reviewers else "None"

    # Changed files and modules
    modules = set()
    file_lines = []
    for f in files[:15]:  # Show up to 15 files
        mod = infer_module_from_file2(f)
        modules.add(mod)
        file_lines.append(f"• `{f}` _(module: {mod})_")
    more_files = "\n...and more" if len(files) > 15 else ""
    modules_line = ", ".join(sorted(modules)) if modules else "Unknown"

    # Channel to modules mapping (all modules per channel in one list)
    channel_to_modules = {
        "pack-lakitu-qa": ["android", "pointshub", "pack-lakitu", "android-guild"],
        "guild-qa": ["app", "guild-ios", 'g11n'],
        "collective-ereceipt-qa": ["pack-elluminati", "ereceipt", "auth", "src"],
        "pack-felix-qa": ["pack-felix", "felix", "src", "terraform"],
        "pack-midas-qa": ["play", "gameplay", "leaderboard", "friends"],
        "collective-rewarded-apps-qa": ["leaderboard", "friends"],
        "pack-gameplay-qa": ["play", "gameplay"],
        "pack-kallax-qa": ["discover", "categories"],
        "pack-apogee-qa": ["video", "ads", "collections"],
        "pack-famex-qa": ["fetchpay", "famex"],
        "pack-rover-qa-channel": ["lidar", "location services"],
        # Add more as needed
    }
    channel_to_id = {
        "pack-lakitu-qa": "C08JXA5PS00",
        "guild-qa": "CKGFVBNTZ",
        "collective-ereceipt-qa": "C04ADQQN97H",
        "pack-felix-qa": "C089K8PM44R",
        "pack-midas-qa": "C077L0N8WHZ",
        "collective-rewarded-apps-qa": "C06GU3KJH08",
        "pack-gameplay-qa": "C066Q2F9HC6",
        "pack-kallax-qa": "C083ZRKV7FA",
        "pack-apogee-qa": "C082W411ZAB",
        "pack-famex-qa": "C07JWD76LCX",
        "pack-rover-qa-channel": "C08D19XDAHX",
        # Add more as needed
    }
    default_channel = "pack-lakitu-qa"

    # Build a reverse mapping: module -> channel
    module_to_channel = {}
    for channel, mod_list in channel_to_modules.items():
        for m in mod_list:
            module_to_channel[m.lower()] = channel

    # Group modules by channel
    channel_modules = {}
    for module in modules:
        channel = module_to_channel.get(module.lower(), default_channel)
        if channel not in channel_modules:
            channel_modules[channel] = []
        channel_modules[channel].append(module)

    # Suggest QAs for each channel (well formatted)
    channel_suggestions = []
    for channel, mod_list in channel_modules.items():
        channel_id = channel_to_id.get(channel)
        channel_mention = f"<#{channel_id}|{channel}>" if channel_id else channel

        if not channel_id:
            channel_suggestions.append(
                f"*Channel*: `{channel}` (modules: {', '.join(f'`{m}`' for m in mod_list)}): Channel ID not found, please update your mapping."
            )
            continue

        # Get all members in the channel
        members = []
        cursor = None
        while True:
            mem_result = app.client.conversations_members(channel=channel_id, limit=100, cursor=cursor)
            members.extend(mem_result.get("members", []))
            cursor = mem_result.get("response_metadata", {}).get("next_cursor")
            if not cursor or len(members) >= 100:
                break

        # Split QAs into active and non-active
        active_qa_mentions = []
        inactive_qa_mentions = []
        for user_id in members:
            user_info = app.client.users_info(user=user_id)
            profile = user_info["user"]["profile"]
            is_qa = "qa" in (profile.get("title", "") + profile.get("real_name", "") + profile.get("display_name", "")).lower()
            if not is_qa:
                continue
            presence = app.client.users_getPresence(user=user_id)
            if presence.get("presence") == "active":
                active_qa_mentions.append(f"<@{user_id}>")
            else:
                inactive_qa_mentions.append(f"<@{user_id}>")

        channel_lines = [
            f"*Channel*: {channel_mention}",
            f"*Modules*: {', '.join(f'`{m}`' for m in mod_list)}",
        ]
        if active_qa_mentions:
            channel_lines.append(f"*Active QAs:* {', '.join(active_qa_mentions)}")
        else:
            channel_lines.append("_No active QAs found._")

        if inactive_qa_mentions:
            channel_lines.append(f"*Non-active QAs:* {', '.join(inactive_qa_mentions)}")
        else:
            channel_lines.append("_No non-active QAs found._")

        if not active_qa_mentions and not inactive_qa_mentions:
            channel_lines.append("_No QAs found in this channel._")

        channel_suggestions.append("\n".join(channel_lines))

    # Final formatted response
    response_lines = [
        f"*PR Title*: `{pr_title}`",
        f"*Author*: {author}",
        f"*Status*: {status}",
        f"*From Branch*: `{branch_from}` → *To*: `{branch_to}`",
        f"*Reviewers*: {reviewers_line}",
        f"*Created On*: {created_on}",
        f"*PR Link*: <{pr_web_url}|View PR>",
        "",
        f"*Changed Files* ({len(files)}):",
        "\n".join(file_lines) + more_files,
        f"\n*Modules/Packages affected*: {modules_line}" if modules else "",
        "\n*Suggested QAs:*",
        "\n\n".join(channel_suggestions),
    ]
    respond("\n".join(response_lines))

def parse_github_pr_url(pr_url):
    from urllib.parse import urlparse
    # Example: https://github.com/org/repo/pull/1234
    parts = urlparse(pr_url)
    path_parts = parts.path.strip('/').split('/')
    if len(path_parts) >= 4 and path_parts[-2] == "pull":
        owner = path_parts[0]
        repo = path_parts[1]
        pr_number = path_parts[3]
        return owner, repo, pr_number
    return None, None, None

def get_github_pr_details(owner, repo, pr_number, github_token):
    headers = {"Authorization": f"token {github_token}", "Accept": "application/vnd.github.v3+json"}
    pr_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}"
    pr_resp = requests.get(pr_url, headers=headers)
    pr_data = pr_resp.json() if pr_resp.status_code == 200 else {}

    files_url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}/files"
    files_resp = requests.get(files_url, headers=headers)
    changed_files = []
    if files_resp.status_code == 200:
        changed_files = [f['filename'] for f in files_resp.json()]
    return pr_data, changed_files

@app.command("/suggest-qa-github")
def suggest_qa_github_command(ack, respond, command):
    ack()
    pr_link = command.get("text", "").strip()
    if not pr_link or "github.com" not in pr_link:
        respond("Please provide a GitHub PR link. Example: `/suggest-qa-github https://github.com/org/repo/pull/1234`")
        return

    owner, repo, pr_number = parse_github_pr_url(pr_link)
    if not owner:
        respond("Could not parse the GitHub PR link.")
        return

    github_token = os.getenv("GITHUB_TOKEN")
    pr_data, files = get_github_pr_details(owner, repo, pr_number, github_token)

    pr_title = pr_data.get("title", "Unknown")
    author = pr_data.get("user", {}).get("login", "Unknown")
    created_on = pr_data.get("created_at", "Unknown")
    status = pr_data.get("state", "Unknown")
    pr_web_url = pr_data.get("html_url", pr_link)
    branch_from = pr_data.get("head", {}).get("ref", "Unknown")
    branch_to = pr_data.get("base", {}).get("ref", "Unknown")
    reviewers = [r["login"] for r in pr_data.get("requested_reviewers", [])] if pr_data.get("requested_reviewers") else []
    reviewers_line = ", ".join(reviewers) if reviewers else "None"

    modules = set()
    file_lines = []
    for f in files[:15]:
        mod = infer_module_from_file2(f)
        modules.add(mod)
        file_lines.append(f"• `{f}` _(module: {mod})_")
    more_files = "\n...and more" if len(files) > 15 else ""
    modules_line = ", ".join(sorted(modules)) if modules else "Unknown"

    # Channel-to-modules mapping (update as needed!)
    channel_to_modules = {
        "pack-lakitu-qa": ["android", "pointshub", "pack-lakitu", "android-guild"],
        "guild-qa": ["app", "guild-ios", "guild-android", "fetchhop"],
        "collective-ereceipt-qa": ["pack-elluminati", "ereceipt", "auth", "src"],
        "pack-felix-qa": ["pack-felix", "felix", "src", "terraform"],
        "pack-midas-qa": ["play", "gameplay", "leaderboard", "friends"],
        "collective-rewarded-apps-qa": ["leaderboard", "friends"],
        "pack-gameplay-qa": ["play", "gameplay"],
        "pack-kallax-qa": ["discover", "categories"],
        "pack-apogee-qa": ["video", "ads", "collections"],
        "pack-famex-qa": ["fetchpay", "famex"],
        "pack-rover-qa-channel": ["lidar", "location services"],
        # Add more as needed
    }
    channel_to_id = {
        "pack-lakitu-qa": "C08JXA5PS00",
        "guild-qa": "CKGFVBNTZ",
        "collective-ereceipt-qa": "C04ADQQN97H",
        "pack-felix-qa": "C089K8PM44R",
        "pack-midas-qa": "C077L0N8WHZ",
        "collective-rewarded-apps-qa": "C06GU3KJH08",
        "pack-gameplay-qa": "C066Q2F9HC6",
        "pack-kallax-qa": "C083ZRKV7FA",
        "pack-apogee-qa": "C082W411ZAB",
        "pack-famex-qa": "C07JWD76LCX",
        "pack-rover-qa-channel": "C08D19XDAHX",
        # Add more as needed
    }
    default_channel = "pack-lakitu-qa"

    # Build reverse module->channel map
    module_to_channel = {}
    for channel, mod_list in channel_to_modules.items():
        for m in mod_list:
            module_to_channel[m.lower()] = channel

    # Group modules by channel
    channel_modules = {}
    for module in modules:
        channel = module_to_channel.get(module.lower(), default_channel)
        if channel not in channel_modules:
            channel_modules[channel] = []
        channel_modules[channel].append(module)

    # Suggest QAs for each channel
    channel_suggestions = []
    for channel, mod_list in channel_modules.items():
        channel_id = channel_to_id.get(channel)
        channel_mention = f"<#{channel_id}|{channel}>" if channel_id else channel

        if not channel_id:
            channel_suggestions.append(
                f"*Channel*: `{channel}` (modules: {', '.join(f'`{m}`' for m in mod_list)}): Channel ID not found, please update your mapping."
            )
            continue

        # Get all members in the channel
        members = []
        cursor = None
        while True:
            mem_result = app.client.conversations_members(channel=channel_id, limit=100, cursor=cursor)
            members.extend(mem_result.get("members", []))
            cursor = mem_result.get("response_metadata", {}).get("next_cursor")
            if not cursor or len(members) >= 100:
                break

        # Split QAs by active/non-active
        active_qa_mentions = []
        inactive_qa_mentions = []
        for user_id in members:
            user_info = app.client.users_info(user=user_id)
            profile = user_info["user"]["profile"]
            is_qa = "qa" in (profile.get("title", "") + profile.get("real_name", "") + profile.get("display_name", "")).lower()
            if not is_qa:
                continue
            presence = app.client.users_getPresence(user=user_id)
            if presence.get("presence") == "active":
                active_qa_mentions.append(f"<@{user_id}>")
            else:
                inactive_qa_mentions.append(f"<@{user_id}>")

        channel_lines = [
            f"*Channel*: {channel_mention}",
            f"*Modules*: {', '.join(f'`{m}`' for m in mod_list)}",
        ]
        if active_qa_mentions:
            channel_lines.append(f"*Active QAs:* {', '.join(active_qa_mentions)}")
        else:
            channel_lines.append("_No active QAs found._")

        if inactive_qa_mentions:
            channel_lines.append(f"*Non-active QAs:* {', '.join(inactive_qa_mentions)}")
        else:
            channel_lines.append("_No non-active QAs found._")

        if not active_qa_mentions and not inactive_qa_mentions:
            channel_lines.append("_No QAs found in this channel._")

        channel_suggestions.append("\n".join(channel_lines))

    # Final formatted response
    response_lines = [
        f"*PR Title*: `{pr_title}`",
        f"*Author*: {author}",
        f"*Status*: {status}",
        f"*From Branch*: `{branch_from}` → *To*: `{branch_to}`",
        f"*Reviewers*: {reviewers_line}",
        f"*Created On*: {created_on}",
        f"*PR Link*: <{pr_web_url}|View PR>",
        "",
        f"*Changed Files* ({len(files)}):",
        "\n".join(file_lines) + more_files,
        f"\n*Modules/Packages affected*: {modules_line}" if modules else "",
        "\n*Suggested QAs:*",
        "\n\n".join(channel_suggestions),
    ]
    respond("\n".join(response_lines))

if __name__ == "__main__":
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    SocketModeHandler(app, os.getenv("SLACK_APP_TOKEN")).start()
