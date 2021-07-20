#!/usr/local/bin/python3.7

import datetime
import logging
import os
import re
import serial
import smbus
import sys
import time
import sched
import wget
import RPi.GPIO as GPIO
from threading import Timer
from pprint import pprint
from optparse import OptionParser
#from ConfigParser import SafeConfigParser
from telegram import (Poll, ParseMode, KeyboardButton, KeyboardButtonPollType,
                      ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton)
from telegram.ext import (Updater, CommandHandler, PollAnswerHandler, PollHandler, MessageHandler,
                          Filters, CallbackQueryHandler)
import urllib3
import tools


# setup alarm logger
alarm_logger = logging.getLogger('alarm_log')
alarm_logger.setLevel(logging.INFO)
alarm_fh = logging.FileHandler('alarm_log')
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
alarm_fh.setFormatter(formatter)
alarm_logger.addHandler(alarm_fh)

# setup alarm passives logger
passives_logger = logging.getLogger('passives_log')
passives_logger.setLevel(logging.INFO)
passives_fh = logging.FileHandler('passives_log')
passives_fh.setFormatter(formatter)
passives_logger.addHandler(passives_fh)

# setup gate logger
gate_logger = logging.getLogger('gate_log')
gate_logger.setLevel(logging.INFO)
gate_fh = logging.FileHandler('gate_log')
gate_fh.setFormatter(formatter)
gate_logger.addHandler(gate_fh)

# setup msg logger
msg_logger = logging.getLogger('msg_log')
msg_logger.setLevel(logging.INFO)
msg_fh = logging.FileHandler('msg_log')
msg_fh.setFormatter(formatter)
msg_logger.addHandler(msg_fh)

# record the start time so we know how long we have been running
start_time = time.time()

# possible input pin values
LOW   = 0
HIGH  = 1

# pin types to determine which sensors are used for stay and armed modes
NA    = 0  # Not Alarm
EXT   = 1  # External: such as garden beams
TRANS = 2  # Transitions: such as doors
INT   = 3  # Internal: such as PIRs


# basic class to store pin parameters
class InputPin(object):

    def __init__(self, pin_num, name, type, state, high, low):
        """sets the parameters for the group"""
        self.pin_num    = pin_num  # i2c number
        self.name       = name
        self.state      = state
        self.type       = type
        self.prev_state = state
        self.high       = high
        self.low        = low

# set up the list of pins for the alarm sensors
pins = [
        InputPin( 0, 'large garage door',  TRANS, LOW,  "opened", "closed"),
        InputPin( 1, 'back door',          TRANS, LOW,  "opened", "closed"),
        InputPin( 2, 'sliding door',       TRANS, LOW,  "opened", "closed"),
        InputPin( 3, 'garage door',        TRANS, LOW,  "opened", "closed"), # find why this is triggering when it does not change
        InputPin( 4, 'front door',         TRANS, LOW,  "opened", "closed"),
        InputPin( 5, 'vehicle gate',       NA,    LOW,  "opened", "closed"), # find why this is triggering multiple times when opened
        InputPin( 6, 'yard pir',           EXT,   LOW,  "triggered", "untriggered"), # courtyard PIR
        InputPin( 7, 'yard pir tamper',    EXT,   LOW,  "triggered", "untriggered"),

        InputPin( 8, 'lounge pir',         INT,   LOW,  "triggered", "untriggered"),
        InputPin( 9, 'lounge pir tamper',  INT,   LOW,  "triggered", "untriggered"),
        InputPin(10, 'alley pir',          EXT,   LOW,  "triggered", "untriggered"), # Alley PIR
        InputPin(11, 'alley pir tamper',   EXT,   LOW,  "triggered", "untriggered"),
        InputPin(12, 'kitchen pir',        INT,   LOW,  "triggered", "untriggered"),  # kitchen PIR
        InputPin(13, 'kitchen pir tamper', INT,   LOW,  "triggered", "untriggered"),
        InputPin(14, 'garden pir',         EXT,   LOW,  "triggered", "untriggered"),                 # Garden  PIR
        InputPin(15, 'garden pir tamper',  EXT,   LOW,  "triggered", "untriggered"),

        InputPin(16, 'unused1',            NA,   HIGH, "triggered", "untriggered"),
        InputPin(17, 'unused2',            NA,   HIGH, "triggered", "untriggered"),
        InputPin(18, 'unused3',            NA,   LOW,  "triggered", "untriggered"),
        InputPin(19, 'unused4',            NA,   LOW,  "triggered", "untriggered"),
        InputPin(20, 'unused5',            NA,   LOW,  "triggered", "untriggered"),
        InputPin(21, 'unused6',            NA,   LOW,  "triggered", "untriggered"),
        InputPin(22, 'unused 7',           NA,   LOW,  "triggered", "untriggered"),
        InputPin(23, 'unused 8',           NA,   LOW,  "triggered", "untriggered"),

        InputPin(24, 'unused 9',           NA,    LOW,  "triggered", "untriggeres"),
        InputPin(25, 'unused 10',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(26, 'unused 11',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(27, 'unused 12',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(28, 'unused 13',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(29, 'unused 14',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(30, 'unused 15',          NA,    LOW,  "triggered", "untriggered"),
        InputPin(31, 'unused 16',          NA,    LOW,  "triggered", "untriggered")]

# set up the list of pins for the outputs
#siren_relay_o  = Pin(24, 'siren',       NA, LOW)
#garage_relay_o = Pin(25, 'garage open', NA, LOW)
#gate_relay_o   = Pin(26, 'gate open',   NA, LOW)
#fence_relay_o  = Pin(27, 'fence set',   NA, LOW)

# set up the list of pins for the receivers
#reciever_0 = Pin(18, 'receiver 0', NA, LOW)
#reciever_1 = Pin(19, 'receiver 1', NA, LOW)
#reciever_2 = Pin(20, 'receiver 2', NA, LOW)
#reciever_3 = Pin(21, 'receiver 3', NA, LOW)
#reciever_4 = Pin(22, 'receiver 4', NA, LOW)
#reciever_5 = Pin(23, 'receiver 5', NA, LOW)

# output pins
SIREN_PIN     = 27
GATE_PIN      = 18
GARAGE_PIN    = 17
FENCE_PIN     = 22
INTERRUPT_PIN = 23

# gpio initialisation
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(SIREN_PIN,   GPIO.OUT)
GPIO.setup(GARAGE_PIN,  GPIO.OUT)
GPIO.setup(GATE_PIN,    GPIO.OUT)
GPIO.setup(FENCE_PIN,   GPIO.OUT)
GPIO.output(SIREN_PIN,  GPIO.HIGH)
GPIO.output(GARAGE_PIN, GPIO.HIGH)
GPIO.output(GATE_PIN,   GPIO.HIGH)
GPIO.output(FENCE_PIN,  GPIO.HIGH)
GPIO.setup(INTERRUPT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)  


# basic class to store group parameters
class Group(object):

    def __init__(self, name, ids, cmds, keyboard):
        """sets the parameters for the group"""
        self.name = name
        self.ids  = ids
        self.cmds = cmds
        self.keyboard = keyboard


# keyboard to send to the admin group with each message
admin_keyboard = ReplyKeyboardMarkup([['alarm stay'     ],['alarm disarm'    ],
                                      ['alarm arm'      ],['panic off'       ],
                                      ['light garden on'],['light garden off'],
                                      ['light alley on' ],['light alley off' ],
                                      ['gate open'      ],['gate ped'        ],
                                      #['garage open'    ],['garage state'    ],
                                      #['fence toggle'   ],['fence state'     ],
                                      ['panic'          ],['panic silent'    ],
                                      #['log alarm'      ],['log msg'         ],
                                      ['ping'           ],['uptime'          ]],
                                    one_time_keyboard=False,
                                    resize_keyboard=True)

# keyboard to send to the gate group with each message
gate_keyboard = ReplyKeyboardMarkup([['gate open'], ['gate ped'],['ping']])

# keyboard to send to the garage group with each message
garage_keyboard = ReplyKeyboardMarkup([['gate open'], ['gate ped'],['ping'],['garage']])


# instantiate the groups
#                       Lisse       Wes
admin_chats = Group('Admin', [-177612403, 327831957], ['gate', 'garage', 'fence', 'alarm', 'ping', 'log', 'panic', 'cam', 'uptime', 'light'], admin_keyboard)
#                      Lisse Gate Group
gate_chats = Group('Gate', [-196606743, -390335706], ['gate', 'ping'], gate_keyboard)
#                      Lisse Garage Group
garage_chats = Group('Garage', [-223667391], ['gate', 'garage', 'ping'], garage_keyboard)
#
log_chats = Group('Logger', [-333241503],[], garage_keyboard)


# add all the groups to the groups list
groups = [admin_chats, gate_chats, garage_chats, log_chats]


class Alarm(object):

    def __init__(self, *args, **kwargs):        
        self.counter   = 0
        self.trig      = True

        self.DISARMED  = 0
        self.STAY      = 1
        self.ARMED     = 2
        
        self.UNTRIGGERED = 0
        self.TRIGGERED   = 1

        self.LOW  = 0
        self.HIGH = 1
        
        # local logs, used to reply to log request messages
        self.local_log_sensors = []
        
        # list to decode alarm stated to a string
        self.STATES      = ["disarmed", "stay", "armed"]
        self.TRIG_STATES = ["untriggered", "triggered"]

        # set which types of pins are used for which mode
        self.stay_types  = [EXT, TRANS]
        self.armed_types = [EXT, TRANS, INT]

        # configure i2c
        print("configuring I2C interface..")
        self.i2c = smbus.SMBus(1)
        self.i2c_addr = [0x3A, 0x38, 0x3B, 0x3E]
        self.i2c_lights_addr = 0x9
        self._config_i2c_pins()
        print("I2C interface configured")

        self.regex = re.compile(',...')
        alarm_logger.info("System startup")
        
        #self.state = self.DISARMED
        self.set_alarm_state(self.DISARMED)

        # lissebot
        self.token = sys.argv[1]

        # attach the gpio interrupt 
        GPIO.add_event_detect(INTERRUPT_PIN, GPIO.FALLING, callback=self._check_inputs, bouncetime=100)
        
        # Create the Updater and pass it your bot's token.
        self.updater = Updater(self.token, use_context=True)
        dp = self.updater.dispatcher
        # add handlers for the start command and button pressed event
        dp.add_handler(CommandHandler('start', self.start))
        # handles all other messages to the bot
        dp.add_handler(MessageHandler(Filters.regex(r"."), self.on_chat_message))

        # Start the Bot
        self.updater.start_polling()
    
        # Run the bot until the user presses Ctrl-C or the process receives SIGINT, SIGTERM or SIGABRT
        self.updater.idle()

        # timer to check if the garage door is open, it runs every 5min
        #self.s = sched.scheduler(time.time, time.sleep)
        #self.s.enter(1, 1, self._check_garage_state, ({'placeholder': 0}))
        #self.s.run()

        #Timer(10, self._check_garage_state, ({})).start()

        #super(Alarm, self).__init__(*args, **kwargs)


    def start():
        pass

    def _check_garage_state(self):
        """
        checks the state of the garage and if it is open it sends a message to the admin group
        and then reschedules itself to run again in 5min
        """
        for i, pin in enumerate(pins):
            if pin.name == 'large garage door' and pin.state == 1:
                msg_str = 'garage door still open'
                self.send_alarm_msg(msg_str)
                alarm_logger.warning(msg_str)
                print(msg_str)
        print('checking garage')
        #Timer(10, self._check_garage_state, ({})).start()
        #self.s.enter(300, 1, self._check_garage_state, ({'placeholder': 0}))
        
    def _config_i2c_pins(self):
        """write all Fs to the i2c pins to set them up with pullup resistors"""
        for addr in self.i2c_addr:
            print(addr)
            self.i2c.write_byte(addr, 0xFF)
        pass

    def _get_alarm_inputs(self):
        """read the states of all the inputs over i2c"""
        self.sensors = []
        time.sleep(0.05)
        for addr in self.i2c_addr:
            self.sensors = self.sensors + list('{0:0b}'.format(0x100 + self.i2c.read_byte(addr))[1:9])
        time.sleep(0.05)
        #print(self.sensors)

    def set_alarm_state(self, state=0):
        """changes the alarm state"""
        s = 'Alarm set to %s' % self.STATES[state]
        if state == self.DISARMED:
            sirenOff()
        alarm_logger.info(s)
        print(s)
        self.state = state
        self.trigger_state = self.UNTRIGGERED
        self._set_pin_initial_states()

    def _set_pin_initial_states(self):
        """when the alarm is set this reads in the current state of each of the inputs"""
        self._get_alarm_inputs()
        for i, pin in enumerate(pins):
            pin.state = int(self.sensors[i])

    def flip_light(self, position, state):
        # read the current state of the lights
        l = list('{0:0b}'.format(0x100 + self.i2c.read_byte(self.i2c_lights_addr))[1:9])
        l.reverse()
        print(l)
        # if light is not in the requested state
        # the relays are inverted hence the == rather than !=
        if int(l[position]) == state: 
            self.i2c.write_byte(self.i2c_lights_addr, 0x1<<position)
            if state == 1:
                return 'Light on'
            else:
                return 'Light off'
        # if light is currently in the requested
        else:
            if state == 1:
                return 'Light already on'
            else:
                return 'Light already off'

    # the placeholder is here to make the callback work, for some reason the callback
    # calls the function with 2 arguments. 
    def _check_inputs(self, placeholder):
        """This is the primary function of the alarm class, it runs though the
        inputs and checks if any have changed since last read. If any have then
        then the alarm state is checked to determine whether the alarm should be
        triggered. This function is now only called when an interrupt is detected.
        """
        print("Interrupt")
        self._get_alarm_inputs()

        for i, pin in enumerate(pins):
            if pin.state != int(self.sensors[i]):
                pin.state = int(self.sensors[i])
                s = '%s %s' % (pin.name, pin.high if pin.state else pin.low)
                self.local_log_sensors += [s]
                if pin.name == 'vehicle gate':
                    gate_logger.info(s)
                elif pin.type == INT:
                    passives_logger.info(s)
                else:
                    alarm_logger.info(s)
                print(s)

                # DISARMED state, dont do anything
                if self.state == self.DISARMED:
                    pass

                # STAY state, check if pin type is part of the stay group
                elif self.state == self.STAY:
                    if pin.type in self.stay_types:
                        if self.trigger_state == self.UNTRIGGERED:
                            s = 'Alarm triggered, %s %s' % (pin.name, pin.high if pin.state else pin.low)
                            print(s)
                            alarm_logger.warning(s)
                            # turn on the outside lights
                            if tools.dark_in_cpt():
                                self.flip_light(0,1)
                                self.flip_light(1,1)
                            beepSiren(1)
                            self.send_alarm_msg(s)
                        self.trigger_state = self.TRIGGERED

                # ARMED state, check if pin type is part of the armed group
                elif self.state == self.ARMED:
                    if pin.type in self.armed_types:
                        if self.trigger_state == self.UNTRIGGERED:
                            s = 'Alarm triggered, %s %s' % (pin.name, pin.high if pin.state else pin.low)
                            print("here")
                            print(s)
                            alarm_logger.warning(s)
                            # turn on the outside lights
                            if tools.dark_in_cpt():
                                self.flip_light(0,1)
                                self.flip_light(1,1)
                            beepSiren(1)
                            self.send_alarm_msg(s)
                        self.trigger_state = self.TRIGGERED

                # TRIGGERED state, dont do anything
                #if self.state == self.TRIGGERED:
                #    pass
        #self.trig = False
        #self.s.enter(0.1, 1, self._check_inputs, ({'placeholder': 0}))

    def send_alarm_msg(self, msg_str):
        #self.bot.sendMessage(327831957,  msg_str)
        #self.bot.sendMessage(-177612403, msg_str)
        print(len(msg_str))
        print(len(msg_str.encode('utf-16')))
        self.updater.bot.send_message("-177612403", text=msg_str)

    def on_chat_message(self, update, context):

        #pprint(msg)
        log_str = ''

        # get the chat_id and command from the message
        #if telepot.flavor(msg) == 'chat':
        #    chat_id = msg['chat']['id']
        #    command = msg['text']
        #    uid = msg['from']['id']
        #elif telepot.flavor(msg) == 'callback_query':
        #    chat_id = msg['message']['chat']['id']
        #    command = msg['data']
        #    uid = msg['from']['id']

        # if the message is from a group
        #if msg['chat']['type'] == 'group':
        #    log_str = "Msg received: '%s' from user %s (%s) in group '%s' (%s)" % (command, msg['from']['first_name'], uid, msg['chat']['title'], chat_id)
        ## if the message is from an individual
        #elif msg['chat']['type'] == 'private':
        #    log_str = "Msg received: '%s' from user %s (%s) in private chat" % (command, msg['from']['first_name'], uid)
        #msg_logger.info(log_str)

        chat_id = update.message.chat_id
        # condition the command
        command = str(update.message.text).lower()
        command = command.replace('_',' ')
        if command.startswith('/'):
            command = command[1:]
        command = command.split(' ')

        print(chat_id)
        print(command)

        # check if the group is in the list of groups
        current_group = None
        for g in groups:
            if chat_id in g.ids:
                current_group = g

        resp_msg = ''

        if current_group is not None:
            if command[0] in current_group.cmds:
                # gate
                if command[0] == 'gate':
                    if command[1] == 'open':
                        # check state
                        toggleGate(0)
                        resp_msg = 'Gate opened'
                    elif command[1] == 'ped':
                        # check state
                        toggleGate(2)
                        resp_msg = 'Gate opened for pedestrian'
                    elif command[1] == 'state':
                        # check state
                        resp_msg = 'Gate is %s' % (pins[0].high if pins[0].state else pins[0].low)
                    else:
                        resp_msg = 'I dont understand %s' % command[1]
                #if command[0] == 'gate':
                #    if len(command) > 1:
                #        if command[1] == 'state':
                #            resp_msg = 'Gate is %s' % (pins[5].high if pins[5].state else pins[5].low)
                #        elif command[1] == 'open':
                #            if pins[5].state == self.LOW:
                #                toggleGate(0)
                #                # wait until the gate door sensor goes high
                #                #while pins[0].state != self.HIGH:
                #                #    time.sleep(0.2)
                #                time.sleep(0.5)
                #                resp_msg = 'Gate is %s' % (pins[5].high if pins[5].state else pins[5].low)
                #            else:
                #                resp_msg = 'Gate is already open'
                #        elif command[1] == 'close':
                #            if pins[5].state == self.HIGH:
                #                toggleGate(0)
                #                # wait until the garage door sensor goes low
                #                #while pins[0].state != self.LOW:
                #                #    time.sleep(0.2)
                #                time.sleep(0.5)
                #                resp_msg = 'Gate is %s' % (pins[5].high if pins[5].state else pins[5].low)
                #            else:
                #                resp_msg = 'Gate is already closed'
                #        elif command[1] == 'ped':
                #            toggleGate(2)
                #            resp_msg = 'Gate is %s' % (pins[5].high if pins[5].state else pins[5].low)
                #        else:
                #            resp_msg = 'I dont understand %s' % command[1]

                # alarm
                if command[0] == 'light':
                    if command[1] == "garden":
                        if command[2] == 'on':
                            resp_msg = self.flip_light(0, 1)
                        elif command[2] == 'off':
                            resp_msg = self.flip_light(0, 0)
                        else:
                            resp_msg = 'What must I do with the light?'
                    if command[1] == "alley":
                        if command[2] == 'on':
                            resp_msg = self.flip_light(1, 1)
                        elif command[2] == 'off':
                            resp_msg = self.flip_light(1, 0)
                        else:
                            resp_msg = 'What must I do with the light?'

                if command[0] == 'alarm':
                    if command[1] == 'arm':
                        self.set_alarm_state(self.ARMED)
                        resp_msg = 'Alarm armed'
                    elif command[1] == 'disarm':
                        self.set_alarm_state(self.DISARMED)
                        # turn off both outside lights when disarmed
                        self.flip_light(0,0)
                        self.flip_light(1,0)
                        resp_msg = 'Alarm disarmed'
                    elif command[1] == 'stay':
                        self.set_alarm_state(self.STAY)
                        resp_msg = 'Alarm set to stay'
                    elif command[1] == 'state':
                        #self.STAY
                        resp_msg = 'Alarm is currently set to %s' % self.STATES[self.state]
                        #resp_msg = 'ToDo: Send alarm logs'
                    else:
                        resp_msg = 'I dont understand %s' % command[1]

                # ping
                if command[0] == 'ping':
                    resp_msg = 'pong'

                # uptime
                if command[0] == 'uptime':
                    resp_msg = str(datetime.timedelta(seconds=int(time.time())-int(start_time)))

                # log
                if command[0] == 'log':
                    resp_msg = "Log messages\n"
                    if command[1] == 'alarm':
                        stdin, stdout = os.popen2('tail -n '+'10'+'0'+' '+'alarm_log')
                        stdin.close()
                        lines = stdout.readlines()
                        stdout.close()
                        print('sending last 20 log msgs')
                        for line in lines[-20: ]:
                            resp_msg += line.replace('\n\n','\n').replace('2019-', '').replace(' - INFO - ', ' ').replace(re.findall(self.regex, line)[0], '')
                        self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                        print(resp_msg)
                        print('sending last log msgs')
                        resp_msg = ''
                    
                    elif command[1] == 'gate':
                        stdin, stdout = os.popen2('tail -n '+'10'+'0'+' '+'gate_log')
                        stdin.close()
                        lines = stdout.readlines()
                        stdout.close()
                        print('sending last 20 log msgs')
                        for line in lines[-20: ]:
                            resp_msg += line.replace('\n\n','\n').replace('2019-', '').replace(' - INFO - ', ' ').replace(re.findall(self.regex, line)[0], '')
                        self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                        print('sending last log msgs')
                        resp_msg = ''

                    elif command[1] == 'msg':
                        stdin, stdout = os.popen2('tail -n '+'10'+'0'+' '+'msg_log')
                        stdin.close()
                        lines = stdout.readlines()
                        stdout.close()
                        print('sending last 20 log msgs')
                        for line in lines[-20: ]:
                            resp_msg += line.replace('\n\n','\n').replace('2019-', '').replace(' - INFO - ', ' ').replace(re.findall(self.regex, line)[0], '')
                        self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                        print('sending last log msgs')
                        resp_msg = ''
                    elif command[1] == 'passives':
                        stdin, stdout = os.popen2('tail -n '+'10'+'0'+' '+'passives_log')
                        stdin.close()
                        lines = stdout.readlines()
                        stdout.close()
                        print('sending last 20 log msgs')
                        for line in lines[-20: ]:
                            resp_msg += line.replace('\n\n','\n').replace('2019-', '').replace(' - INFO - ', ' ').replace(re.findall(self.regex, line)[0], '')
                        self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                        print('sending last log msgs')
                        resp_msg = ''
                    elif command[1] == 'sensors':
                        print('sending last 20 sensor msgs')
                        print(self.local_log_sensors)
                        #for line in self.local_log_sensors[-5: ]:
                        #    resp_msg += line.replace('\n\n','\n').replace('2019-', '').replace(' - INFO - ', ' ').replace(re.findall(self.regex, line)[0], '')
                        #self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                        print('sending last log msgs')
                        resp_msg = ''
                    #resp_msg = 'not implemented'
                    #pass

                # garage
                if command[0] == 'garage':
                    if len(command) > 1:
                        if command[1] == 'state':
                            resp_msg = 'Garage is %s' % (pins[0].high if pins[0].state else pins[0].low)
                        elif command[1] == 'open':
                            #if pins[0].state == self.LOW:
                                toggleGarage()
                                # wait until the garage door sensor goes high
                                #while pins[0].state != self.HIGH:
                                #    time.sleep(0.2)
                                time.sleep(0.5)
                                resp_msg = 'Garage is %s' % (pins[0].high if pins[0].state else pins[0].low)
                            #else:
                            #    resp_msg = 'Garage is already open'
                        #elif command[1] == 'close':
                        #    if pins[0].state == self.HIGH:
                        #        toggleGarage()
                        #        # wait until the garage door sensor goes low
                        #        #while pins[0].state != self.LOW:
                        #        #    time.sleep(0.2)
                        #        time.sleep(0.5)
                        #        resp_msg = 'Garage is %s' % (pins[0].high if pins[0].state else pins[0].low)
                        #    else:
                        #        resp_msg = 'Garage is already closed'
                        else:
                            resp_msg = 'I dont understand %s' % command[1]

                # panic
                if command[0] == 'panic':
                    if len(command) == 1:
                        sirenOn()
                        resp_msg = 'Panic activated'
                    elif command[1] == 'silent':
                        resp_msg = 'Silent panic activated'
                    elif command[1] == 'off':
                        sirenOff()
                        resp_msg = 'Panic deactivated'
                    else:
                        resp_msg = 'I dont understand %s' % command[1]

                # fence
                if command[0] == 'fence':
                    if len(command) > 1:
                        if command[1] == 'state':
                            resp_msg = 'Fence is %s' % (pins[14].high if pins[14].state else pins[14].low)
                        elif command[1] == 'on':
                            if pins[14].state == self.LOW:
                                toggleFence()
                                # wait until the fence state sensor goes high
                                #while pins[16].state != self.HIGH:
                                #    time.sleep(0.2)
                                time.sleep(0.5)
                                resp_msg = 'Fence is %s' % (pins[14].high if pins[14].state else pins[14].low)
                            else:
                                resp_msg = 'Fence is already on'
                        elif command[1] == 'off':
                            if pins[14].state == self.HIGH:
                                toggleFence()
                                # wait until the fence state sensor goes low
                                #while pins[16].state != self.LOW:
                                #    time.sleep(0.2)
                                time.sleep(0.5)
                                resp_msg = 'Fence is %s' % (pins[14].high if pins[14].state else pins[14].low)
                            else:
                                resp_msg = 'Fence is already off'
                        else:
                            resp_msg = 'I dont understand %s' % command[1]

                # cameras
                if command[0] == 'cam':
                    if command[1] == '1':
                        urls = ['http://10.0.0.150/image.jpg']
                    elif command[1] == '2':
                        urls = ['http://10.0.0.151/image.jpg']
                    elif command[1] == '3':
                        urls = ['http://10.0.0.152/image.jpg']
                    elif command[1] == '4':
                        urls = ['http://10.0.0.153/image.jpg']
                    elif command[1] == 'all':
                        urls = ['http://10.0.0.150/image.jpg', 'http://10.0.0.151/image.jpg', 'http://10.0.0.152/image.jpg', 'http://10.0.0.153/image.jpg']
                    # get images from cameras
                    for url in urls:
                        filename = wget.download(url)
                        f = open(filename, 'rb')
                        bot.sendPhoto(chat_id, f)

                # send response message
                if resp_msg != '':
                    #self.bot.sendMessage(chat_id, resp_msg, reply_markup=current_group.keyboard)
                    update.message.reply_text(resp_msg, reply_markup=current_group.keyboard)
                    msg_logger.info("Msg sent: '%s' to chat_id %s" % (resp_msg, chat_id))

            # we don't recognise the command
            else:
                resp_msg = 'I dont understand "%s"' % command[0]
                #self.bot.sendMessage(chat_id, resp_msg)
                update.message.reply_text(resp_msg, reply_markup=current_group.keyboard)
                msg_logger.info("Msg sent: '%s' to chat_id %s" % (resp_msg, chat_id))

        # the sender/group is not authorised
        else:
            resp_msg = 'You are not authorised'
            #self.bot.sendMessage(chat_id, resp_msg)
            update.message.reply_text(resp_msg)
            msg_logger.warning("Msg sent: '%s' to chat_id %s" % (resp_msg, chat_id))


###############################################################################
#                                                                             #
#                       Functions to control gpios                            #
#                                                                             #
###############################################################################

def toggleGate(duration):
    GPIO.output(GATE_PIN, False)
    time.sleep(0.5)
    GPIO.output(GATE_PIN, True)
    if duration > 0:
        time.sleep(duration)
        GPIO.output(GATE_PIN, False)
        time.sleep(0.5)
        GPIO.output(GATE_PIN, True)
    print('Toggling gate state')


def toggleFence():
    GPIO.output(FENCE_PIN, False)
    time.sleep(0.5)
    GPIO.output(FENCE_PIN, True)
    print('Toggling fence state')


def toggleGarage():
    GPIO.output(GARAGE_PIN, False)
    time.sleep(0.5)
    GPIO.output(GARAGE_PIN, True)
    print('toggled garage')


def beepSiren(duration):
    GPIO.output(SIREN_PIN, False)
    print('siren pulsed')
    time.sleep(duration)
    GPIO.output(SIREN_PIN, True)

def sirenOn():
    GPIO.output(SIREN_PIN, False)
    print('siren on')


def sirenOff():
    #GPIO.output(SIREN_PIN, True)
    print('siren off')


alarm = Alarm()
print('Bot up and ready ...')





