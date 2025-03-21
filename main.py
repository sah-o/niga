import discord
from discord.ext import commands
from discord.ui import Button, View
import io
import barcode
from barcode.writer import ImageWriter
import os

# Load configurations
with open('code.txt', 'r') as f:
    TOKEN = f.read().strip()

with open('id.txt', 'r') as f:
    ADMIN_ID = int(f.read().strip())

# Initialize bot with intents
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Cooldown tracking for each command
cooldowns = {}
COOLDOWN_TIMES = {}

# Barcode templates (store-specific formatting)
BARCODE_FORMATS = {
    'ms': {'prefix': '821', 'barcode_length': 8, 'price_length': 7},
    'waitrose': {'prefix': '10', 'barcode_length': 13, 'price_length': 2},
    'morrisons': {'prefix': '92', 'barcode_length': 13, 'fixed_price': '00113300027'},
    'savers': {'prefix': '97', 'barcode_length': 13, 'price_length': 3},
    'sainsburys': {'prefix': '91', 'barcode_length': (8, 13), 'price_length': 3}
}

# Logs file
LOGS_FILE = 'logs.txt'

# Guides storage
GUIDES = {}

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name}')

@bot.event
async def on_message(message):
    if message.content.startswith('!saho'):
        await show_main_menu(message)
    elif message.content.startswith('!'):
        await handle_category_command(message)
    await bot.process_commands(message)

async def show_main_menu(message):
    """Display the main menu with options."""
    # Create an embed for the banner
    embed = discord.Embed(title="Main Menu", color=0x00ff00)
    embed.set_image(url="https://mega.nz/file/mBQjgYjC#cl4RZSpbsvuD5w5TcXsRQjkKYvd088nOcLeBxUS3xjo")
    embed.add_field(name="Commands", value="Select an option below:", inline=False)

    # Create a view with buttons
    view = View()

    # Button for Generate Barcodes
    generate_button = Button(label="Generate Barcodes", style=discord.ButtonStyle.primary)
    generate_button.callback = lambda interaction: handle_generate_barcodes(interaction)
    view.add_item(generate_button)

    # Button for Promo Codes
    promo_button = Button(label="Promo Codes", style=discord.ButtonStyle.secondary)
    promo_button.callback = lambda interaction: handle_promo_codes(interaction)
    view.add_item(promo_button)

    # Button for New Category
    new_button = Button(label="New Category", style=discord.ButtonStyle.success)
    new_button.callback = lambda interaction: handle_new_category(interaction)
    view.add_item(new_button)

    # Button for Add Guide
    guide_button = Button(label="Add Guide", style=discord.ButtonStyle.primary)
    guide_button.callback = lambda interaction: handle_add_guide(interaction)
    view.add_item(guide_button)

    # Send the embed with buttons
    await message.channel.send(embed=embed, view=view)

async def handle_generate_barcodes(interaction):
    """Handle the Generate Barcodes button."""
    await interaction.response.send_message("**Select a store to generate barcode:**")

    # Create a dropdown for store selection
    view = View()
    select = Select(placeholder="Select a store", options=[
        discord.SelectOption(label="MS", value="ms"),
        discord.SelectOption(label="Waitrose", value="waitrose"),
        discord.SelectOption(label="Morrisons", value="morrisons"),
        discord.SelectOption(label="Savers", value="savers"),
        discord.SelectOption(label="Sainsburys", value="sainsburys")
    ])
    select.callback = lambda i: handle_store_selection(i, select.values[0])
    view.add_item(select)

    await interaction.followup.send(view=view)

async def handle_store_selection(interaction, store):
    """Handle store selection for barcode generation."""
    await interaction.response.send_message(f"Enter the barcode and price for {store} (e.g., `12345678 100`):")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        barcode_num, price = msg.content.split()
        if store == "morrisons" and price:
            await interaction.followup.send("❌ Morrisons does not require a price.", delete_after=10)
            return

        # Generate the barcode
        full_code = generate_store_barcode(store, barcode_num, price)
        barcode_image = generate_barcode_image(full_code)

        # Send the barcode image to the chat
        await interaction.followup.send(file=discord.File(barcode_image, 'barcode.png'))
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ Timed out. Please try again.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

def generate_store_barcode(store, barcode_num, price=None):
    """Generate a barcode string based on store-specific formatting."""
    store = store.lower()
    if store == "morrisons":
        return f"92{barcode_num.zfill(13)}00113300027"
    elif store == "ms":
        return f'821{barcode_num.zfill(8)}{int(price):07d}'
    elif store == "waitrose":
        return f'10{barcode_num.zfill(13)}00{int(price):02d}'
    elif store == "savers":
        return f'97{barcode_num.zfill(13)}{int(price):03d}0'
    elif store == "sainsburys":
        return f'91{barcode_num.zfill(12)}{int(price):03d}0'
    else:
        return barcode_num  # Fallback for unknown stores

def generate_barcode_image(code):
    """Generate a barcode image using Code128 in-memory."""
    writer = ImageWriter()
    barcode_obj = barcode.get('code128', code, writer=writer)
    img_io = io.BytesIO()
    barcode_obj.write(img_io, options={'write_text': False})
    img_io.seek(0)
    return img_io

async def handle_promo_codes(interaction):
    """Handle the Promo Codes button."""
    if not COOLDOWN_TIMES:
        await interaction.response.send_message("❌ No promo codes available.")
        return

    embed = discord.Embed(title="📜 Promo Codes", color=0x00ff00)
    for category, cooldown_seconds in COOLDOWN_TIMES.items():
        cooldown_hours = cooldown_seconds / 3600
        guide = GUIDES.get(category, "No guide available.")
        embed.add_field(
            name=f"🎁 {category.capitalize()}",
            value=f"Trigger Command: `!{category}`\nCooldown: {cooldown_hours}h\nGuide: {guide}",
            inline=False
        )
    await interaction.response.send_message(embed=embed)

async def handle_new_category(interaction):
    """Handle the New Category button."""
    await interaction.response.send_message("Enter the category name and cooldown in hours (e.g., `new_category 24`):")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        name, cooldown = msg.content.split()
        cooldowns[name] = {}
        COOLDOWN_TIMES[name] = int(float(cooldown) * 3600)
        with open(f'{name}.txt', 'w') as f:
            pass  # Create an empty file
        await interaction.followup.send(f"✅ Category '{name}' added with a cooldown of {cooldown} hours.")
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ Timed out. Please try again.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

async def handle_add_guide(interaction):
    """Handle the Add Guide button."""
    await interaction.response.send_message("Enter the category name and guide (e.g., `new_category This is a guide.`):")

    def check(m):
        return m.author == interaction.user and m.channel == interaction.channel

    try:
        msg = await bot.wait_for('message', timeout=60.0, check=check)
        category, *guide_parts = msg.content.split()
        guide = " ".join(guide_parts)
        GUIDES[category] = guide
        await interaction.followup.send(f"✅ Guide added for '{category}'.")
    except asyncio.TimeoutError:
        await interaction.followup.send("⏰ Timed out. Please try again.")
    except Exception as e:
        await interaction.followup.send(f"❌ Error: {str(e)}")

# Run the bot
bot.run(TOKEN)
