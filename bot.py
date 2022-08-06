from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters import Text
from aiogram.utils.callback_data import CallbackData
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove, KeyboardButton
import databases
import aiohttp
import base64

bot_id = '5543570195:AAGNSG9MnSfrh1JsoFnVh16yghuwZ3Z5WFc'
storage = MemoryStorage()
bot = Bot(token=bot_id)
dp = Dispatcher(bot, storage=storage)
database = databases.Database('sqlite+aiosqlite:///heroku.db')
main_kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("Apps' list📝")).add(KeyboardButton("Add app🟣"))
app_cb = CallbackData('app', 'name', 'owner_id')



class Add(StatesGroup):
    app_name = State()
    app_token = State()


class Operation(StatesGroup):
    operation = State()
    dyno_type = State()
    dyno_amount = State()


async def on_startup(_):
    await database.connect()
    query = '''CREATE TABLE IF NOT EXISTS Apps (id INTEGER PRIMARY KEY, name VARCHAR(100), token STRING, owner_id INTEGER)'''
    await database.execute(query)


@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    await message.reply('You can manage your Heroku apps here.\nFor beggining, use /add command(list of all commands - /help)', reply_markup=main_kb)


@dp.message_handler(commands=['help'])
async def help(message: types.Message):
    await message.reply("/add - Add another Heroku app\n\n/list - List of your apps\n*We will store your app's Heroku name and api token.*\nTo interact with your app choose it from /list📝", parse_mode='Markdown', reply_markup=main_kb)


@dp.message_handler(commands=['add'])
@dp.message_handler(Text(equals='add app🟣', ignore_case=True))
async def add_begin(message: types.Message):
    await message.reply("Enter app's name as on Heroku")
    await Add.app_name.set()


@dp.message_handler(state=Add.app_name)
async def receveing_token(message: types.Message, state: FSMContext):
    if 'cancel' in message.text.lower():
        await message.reply('Cancelled', reply_markup=main_kb)
        await state.finish()
        return
    await state.update_data(name=message.text)
    await message.reply('Name saved✔️\nNow send API token from Heroku...')
    await Add.app_token.set()


@dp.message_handler(state=Add.app_token)
async def finishing_add(message: types.Message, state: FSMContext):
    if 'cancel' in message.text.lower():
        await message.reply('Cancelled', reply_markup=main_kb)
        await state.finish()
        return
    token = message.text
    name = await state.get_data()
    query = '''INSERT INTO Apps(name, token, owner_id) VALUES (:name, :token, :owner_id)'''
    values = {'name': name['name'], 'token': token, 'owner_id': message.from_user.id}
    await database.execute(query, values)
    await message.reply(f'Your app *{name["name"]}* saved✔️\nUse /list to view all of your apps📝', parse_mode='Markdown', reply_markup=main_kb)
    await state.finish()


@dp.message_handler(commands=['list'])
@dp.message_handler(Text(equals="apps' list📝", ignore_case=True))
async def list(message: types.Message):
    query = '''SELECT name FROM Apps WHERE owner_id=:owner_id'''
    values = {'owner_id': message.from_user.id}
    names = await database.fetch_all(query, values)
    if names:
        kb = InlineKeyboardMarkup(row_width=1)
        for i in names:
            kb.add(InlineKeyboardButton(text=i[0], callback_data=app_cb.new(name=i[0], owner_id=message.from_user.id)))
        await message.reply('Your apps:', reply_markup=kb)
        return
    await message.reply("You don't have any apps :(", reply_markup=main_kb)


@dp.message_handler(state='*', commands=['cancel'])
@dp.message_handler(Text(contains='cancel', ignore_case=True), state='*')
async def cancel(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if not current_state:
        await message.reply('Nothing to cancel❌', reply_markup=main_kb)
        return
    await state.finish()
    await message.reply('Cancelled✔️', reply_markup=main_kb)


@dp.callback_query_handler(app_cb.filter())
async def process_app(query: types.CallbackQuery, callback_data: dict, state: FSMContext):
    await query.answer()
    await Operation.operation.set()
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton(
        'Scale dynos')).add(KeyboardButton('Remove app from bot❌'))
    await bot.send_message(query.from_user.id, 'Choose action by keyboard:', reply_markup=kb)
    await state.update_data(name=callback_data['name'])
    await state.update_data(owner_id=callback_data['owner_id'])


@dp.message_handler(state=Operation.operation)
async def choose_operation(message: types.Message, state: FSMContext):
    if 'cancel' in message.text.lower():
        await state.finish()
        await message.reply('Cancelled✔️')
        return
    if message.text.lower() not in ['scale dynos', 'remove app from bot❌']:
        await message.reply('❗Choose from keyboard❗')
        return
    if message.text.lower() == 'remove app from bot❌':
        app_data = await state.get_data()
        query = 'DELETE FROM Apps WHERE name=:name AND owner_id=:owner_id'
        params = {'name': app_data['name'], 'owner_id': int(app_data['owner_id'])}
        await database.execute(query, params)
        await message.reply('Done✔️')
        await state.finish()
        return
    kb = ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton('web')).add(KeyboardButton('worker'))
    await message.reply('Choose dyno type:', reply_markup=kb)
    await Operation.dyno_type.set()



@dp.message_handler(state=Operation.dyno_type)
async def choose_dyno_type(message: types.Message, state: FSMContext):
    if 'cancel' in message.text.lower():
        await state.finish()
        await message.reply('Cancelled✔️')
        return
    if message.text.lower() not in ['web', 'worker']:
        await message.reply('❗Choose from keyboard❗')
        return
    await state.update_data(type=message.text)
    await message.reply('Now send an amount:', reply_markup=ReplyKeyboardRemove())
    await Operation.dyno_amount.set()



@dp.message_handler(state=Operation.dyno_amount)
async def choosing_dyno_amount(message: types.Message, state: FSMContext):
    if 'cancel' in message.text.lower():
        await state.finish()
        await message.reply('Cancelled✔️')
        return
    if not message.text.isdigit():
        await message.reply('❗❗Must be a *digit*❗❗', parse_mode='Markdown')
        return
    app_data = await state.get_data()
    query = '''SELECT token FROM Apps WHERE name=:name AND owner_id=:owner_id'''
    token = await database.fetch_one(query, values={'name': app_data['name'], 'owner_id': int(app_data['owner_id'])})
    headers = {
        'Accept': 'application/vnd.heroku+json; version=3',
        'Authorization': str(base64.b64encode(f':{token[0]}'.encode('utf-8')), 'utf-8')
    }
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.patch(f"https://api.heroku.com/apps/{app_data['name']}/formation/{app_data['type']}", json={'quantity': int(message.text)}) as response:
                if response.status == 200:
                    await message.reply('Scaling has done succesfully✔️', reply_markup=main_kb)
                    await state.finish()
                    return
                await message.reply("Scaling couldn't be done❌", reply_markup=main_kb)
                await state.finish()
    except Exception as e:
        await message.reply("❌Error occured during request. Check app's token", reply_markup=main_kb)
        await state.finish()


if __name__ == '__main__':
    executor.start_polling(dp, on_startup=on_startup)
