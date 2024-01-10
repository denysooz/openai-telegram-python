import asyncio
import logging
import openai
import os
import requests
import replicate
from deep_translator import GoogleTranslator
from pydub import AudioSegment
from aiogram import Router
from aiogram import Bot
from aiogram import Dispatcher
from aiogram import F
from aiogram import types
from aiogram.types import URLInputFile
from aiogram.types.message import Message
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.filters.callback_data import CallbackData
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types.callback_query import CallbackQuery
from openai import OpenAI
from PIL import Image
from io import BytesIO

import tokens

router = Router(name = __name__)
class MyCallback(CallbackData,prefix='my'):
  mode: str

class GPTMode(StatesGroup):
  gpt_mode = State()
# Настройка классов
bot = Bot(token=tokens.TOKEN) 
dp = Dispatcher()
dp.include_router(router)
client = OpenAI(api_key=tokens.openai.api_key) 

async def on_startup(storage):
    await storage.set_state(key='1',state=GPTMode.gpt_mode.state)
# Генерация ответа через chatgpt на текстовый промт
async def answerToText(message):
  completion = client.chat.completions.create(
    model="gpt-3.5-turbo-1106",
    messages=[
    {"role": "system", "content": "Ты хороший ассистент."}, 
    {"role": "user", "content": str(message)}
    ],
  )
  await message.answer(completion.choices[0].message.content)

# Генерация ответа через chatgpt на голосовой промт
async def answerToVoice(message: types.Message):
  voice = message.voice
  file_id = voice.file_id
  file = await bot.get_file(file_id)
  file_path = file.file_path
  file_url = f'https://api.telegram.org/file/bot{tokens.TOKEN}/{file_path}'

  ogg_file_content = requests.get(file_url).content
  # oggBuffer = BytesIO()
  # oggInMem = AudioSegment(ogg_file_content, sample_width = 16, frame_rate=48000, channels = 1)
  # oggInMem.export(oggBuffer, format='ogg')
  with open(f'voice_message_{message.message_id}.ogg', 'wb') as ogg_file:
      ogg_file.write(ogg_file_content) 
  vfile = open(f'voice_message_{message.message_id}.ogg', 'rb') 
# Перевод аудиофайла в текст
  transcript = client.audio.transcriptions.create( 
    model="whisper-1",
    file=vfile,
    language="ru",
    temperature=0.8
  )
  completion = client.chat.completions.create( 
    model="gpt-3.5-turbo-1106",
    messages=[
    {"role": "system", "content": "Ты хороший ассистент."},
    {"role": "user", "content": str(transcript.text)}
    ]
  )
  vfile.close() 
  os.remove(f'voice_message_{message.message_id}.ogg')
  await message.answer(transcript.text+"\n\n"+completion.choices[0].message.content)
  
async def answerImage(message,iprompt):
  generated = client.images.generate(
    model="dall-e-2",
    prompt=GoogleTranslator(source='auto', target='en').translate(iprompt),
    n=1,
    size="1024x1024"
  )
  # with requests.get(generated.data[0].url,timeout=None) as response:
  #   imaga = Image.open(BytesIO(response.content))
  #   imaga = imaga.save("picture.jpg")

  await bot.send_photo(message.chat.id,URLInputFile(generated.data[0].url, filename="picture.png"), request_timeout = 60000, reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))

builder = ReplyKeyboardBuilder()
builder.button(text='Режим "Вопрос/ответ"', callback_data=MyCallback(mode='gptmode'))
builder.button(text='Режим "Рисование"', callback_data=MyCallback(mode='imgmode'))
builder.button(text='Помощь', callback_data=MyCallback(mode='about'))


@dp.message(StateFilter(None), Command("start"))
# Получение сообщения
async def echo_message(message: types.Message, state: FSMContext):
    #await state.set_state(GPTMode.gpt_mode)
    await state.update_data(currentMode = '1')
    await message.answer("Welcome", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))
@router.message(StateFilter(None), F.text.lower() == 'режим "вопрос/ответ"')
async def gptModeSwitch1(message, state: FSMContext):
    await state.update_data(currentMode = '1')
    await message.answer("Текущий режим: \"Вопрос-ответ\"", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))
@router.message(StateFilter(None), F.text.lower() == 'режим "рисование"')
async def gptModeSwitch2(message, state: FSMContext):
    await state.update_data(currentMode = '2')
    await message.answer("Текущий режим: \"Рисование\"", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))
@router.message(F.text.lower() == "помощь")
async def ask_about(message: Message):
    await message.answer("Я - бот, который готов ответить на Ваш вопрос или нарисовать картинку по Вашему запросу.\nВ режиме \"Вопрос/ответ\" я расцениваю каждое сообщение как вопрос или задачу и предлагаю ответ.\nВ режиме \"Рисование\" я создаю изображение на основе Вашего сообщения.\nПриятного использования!", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))

# Строки ниже для запуска и работы бота
@router.message(StateFilter(None))
async def ask_gpt_no_prompt(message: Message, state: FSMContext):
  
  print(message.text)
  cMode = await state.get_data()
  if len(cMode.keys()) == 0:
    cMode['currentMode'] = '1'
  print(cMode['currentMode'])
  if cMode['currentMode'] == '1':
    if message.text != None:
      await answerToText(message)
    else:
      await answerToVoice(message)
  elif cMode['currentMode'] == '2':
    if message.text != None:
      await message.answer("Запущена генерация изображения", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))

      await answerImage(message,message.text)
    else:
      voice = message.voice
      file_id = voice.file_id
      file = await bot.get_file(file_id)
      file_path = file.file_path
      file_url = f'https://api.telegram.org/file/bot{tokens.TOKEN}/{file_path}'
      ogg_file_content = requests.get(file_url).content
      with open(f'voice_message_{message.message_id}.ogg', 'wb') as ogg_file:
        ogg_file.write(ogg_file_content) 
      vfile = open(f'voice_message_{message.message_id}.ogg', 'rb') 

      transcript = client.audio.transcriptions.create( 
        model="whisper-1",
        file=vfile,
        language="ru",
        temperature=0.8
      )
      await message.answer(transcript.text+"\n\n"+"Запущена генерация изображения", reply_markup=builder.as_markup(resize_keyboard=True, is_persistent=True))
      await answerImage(message,str(transcript.text))
  
async def main(): 
  logging.basicConfig(level=logging.INFO)
  storage = MemoryStorage()
  await on_startup(storage)
  await dp.start_polling(bot)

if __name__ == "__main__":
  asyncio.run(main())
