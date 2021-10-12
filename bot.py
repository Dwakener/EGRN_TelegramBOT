import requests 
import json
import telebot
import datetime, threading, time
from telebot import types
from pyqiwip2p import QiwiP2P
from pyqiwip2p.types import QiwiCustomer, QiwiDatetime
from datetime import timedelta
import sqlite3
import os.path

p2p = QiwiP2P(auth_key="")
Token=''
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
db_path = os.path.join(BASE_DIR, "order.db")

bot = telebot.TeleBot("", parse_mode=None)
bot.remove_webhook()

def ObjectInfoFull(clientid, cadNomer, nameDOC, typeDoc):
    r = requests.post('https://apiegrn.ru/api/cadaster/objectInfoFull', data = {'query':cadNomer}, headers={'Token': Token})
    js = json.loads(r.text)
    Save_order(js['encoded_object'], nameDOC, typeDoc, clientid)
    
def Save_order(encoded_object, nameDOC, typeDoc, clientid): 
    datastr = {
    "encoded_object" : encoded_object,
    "documents": nameDOC
    }
    r = requests.post('https://apiegrn.ru/api/cadaster/save_order', data=datastr, headers={'Token': Token})
    js = json.loads(r.text)   
    
    ####
    sc = sqlite3.connect(db_path)
    cursor = sc.cursor()
    dictionary = {'clientid':clientid, 'documents_id': str(js['transaction_id']), 'typeDoc':typeDoc, 'status':3, 'nameDOC':nameDOC}    
    query = "insert into orders  values" + str(tuple(dictionary.values())) + ";"
    cursor.execute(query)
    sc.commit()
    cursor.close()
    ###    
    
    info(js['transaction_id'])
    
def info(transaction_id):
    datastr = {
    "id" : transaction_id,
    }
    r = requests.post('https://apiegrn.ru/api/transaction/info', data=datastr, headers={'Token': Token})
    js = json.loads(r.text)
    if js['pay_methods']['PA']['allowed']==True:
        pay(transaction_id,js['pay_methods']['PA']['confirm_code'])
    else:
        print('Оплата с лицевого счета запрещена ')
        
def pay(transaction_id,confirm_code):
    datastr = {
    "id" : transaction_id,
    "confirm":confirm_code
    }
    r = requests.post('https://apiegrn.ru/api/transaction/pay', data=datastr, headers={'Token': Token})
    js = json.loads(r.text)
    if js['paid']==True:
        print('Оплата прошла !!!')
    else:
        print('Оплата не прошла !!!')

@bot.message_handler(commands=['info'])
def color(message):
    print(message.from_user.id)
    bot.send_message(message.from_user.id,'Заказываемый документ\n'+
    'XZP  - Отчет об основных параметрах объекта недвижимости\n'+
    'SOPP - Отчет об изменениях прав на объект недвижимости\n'+ 
    'Формат получаем данных\n'+
    'PDF — Человеко-читаемый формат\n'+
    'HTML — Как веб страница\n'+
    'XML — Технический формат\n'+
    'Пример запроса\n'+
    '46:29:101001:10 XZP PDF\n'+
    '150р документ')

@bot.message_handler(commands=['order'])
def sendorder(message):
    msg = bot.send_message(message.chat.id, 'Пример запроса\n'+'46:29:101001:10 XZP PDF') 
    bot.register_next_step_handler(msg,order)
       
def order(message): 
    cadNomer, nameDOC, typeDoc = message.text.split()
    price = 200
    lifetime = 10
    comment = 'by ЕГРН' 
    bill = p2p.bill(amount=price, lifetime=lifetime, comment=comment)
    link_oplata = bill.pay_url
    bot.send_message(message.from_user.id, 'Приветствуем!\nЗаказ стоит: 150 рублей\nСчет действителен 10 минут\nДля оплаты нажмите на данное слово: '+ str(link_oplata))
    x = threading.Thread(target=functionoplata, args=(message, bill, cadNomer, nameDOC, typeDoc)) #Target - данный параметр принимает переменную, а в нашем варианте функцию которая будет проверять оплату. Args - аргументы, допустим для отправки сообщения.
    x.start() #Запуск потока
    
def functionoplata(message, bill, cadNomer, nameDOC, typeDoc): #Функция, ее можно создавать даже не асинхронной - ведь эта функция выполняется в потоке для пользователя.
    oplata_time = datetime.datetime.now() #Получаем текущее время
    datetime_delta = oplata_time + timedelta(minutes=10) #Получаем разницу между датами.
    while True: #Создание цикла
        status = p2p.check(bill_id=bill.bill_id).status #Проверка статуса оплаты
        if status == 'PAID': #Проверка, на то - дошла ли оплата до бота. Вслучае положительного ответа, он выполняет данный if.
            ObjectInfoFull(message.from_user.id, cadNomer, nameDOC, typeDoc)
            break #Завершение цикла
        elif datetime.datetime.now() > datetime_delta: #Делаем проверку, на время оплаты. То есть в случае неоплаты в течении 7-ми минут, цикл прекращается.
            bot.send_message(message.from_user.id,'Время закончилась, оплата не прошла!')
            break #Завершение цикла
    time.sleep(0.1) #Спим некое время, чтобы бот не крашнулся.


@bot.message_handler(commands=['chek'])
def chek_ms(message):
    ####
    sc = sqlite3.connect(db_path)
    cursor = sc.cursor()
    result = cursor.execute( "SELECT  documents_id, typeDoc, nameDOC from orders  where clientid="+str(message.from_user.id)+" and status=3").fetchall()
    for elem in result:
        #print(result)
        DownloadOrders(message, elem[0],elem[1],elem[2])
    cursor.close()
    ###   

def DownloadOrders(message, documents_id, typeDoc, nameDOC):
    datastr = {
            "id":documents_id
            }
    r = requests.post('https://apiegrn.ru/api/cadaster/orders', data=datastr, headers={'Token': Token})
    js = json.loads(r.text)
    if js['documents'][0]['status']==4:
        datastr = {
            "document_id" : documents_id,
            "format": typeDoc
            }
        r = requests.post('https://apiegrn.ru/api/cadaster/download', data=datastr, headers={'Token': Token})
        data = r.content
        with open(documents_id+'.'+typeDoc, 'wb') as s:
            s.write(data)
        f = open(documents_id+'.'+typeDoc,"rb")
        bot.send_document(message.chat.id,f)
    elif js['documents'][0]['status']==3:  
        bot.send_message(message.chat.id,'Заказ в работе')
    
    
@bot.message_handler(content_types=['text'])   
def mess(message):
    bot.send_message(message.from_user.id, '/info для получения справки.\n/order для формирования заказа.\n/chek для проверки заказа')
    
  
if __name__ == '__main__':
    bot.polling(none_stop=True)