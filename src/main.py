#!/usr/bin/python3

from __future__ import print_function
import argparse
import json
import os.path
import pathlib2 as pathlib
import os
import subprocess
import re
import logging
import time
import random
import sys
import signal
import requests
import io
import yaml
from threading import Thread
import urllib.request
import paho.mqtt.client as mqtt
from pathlib import Path
from Adafruit_IO import MQTTClient


ROOT_PATH = os.path.realpath(os.path.join(__file__, '..', '..'))
USER_PATH = os.path.realpath(os.path.join(__file__, '..', '..','..'))

with open('{}/src/config.yaml'.format(ROOT_PATH),'r', encoding='utf8') as conf:
    configuration = yaml.load(conf)

if 'en' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_en.yaml'.format(ROOT_PATH)
elif 'it' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_it.yaml'.format(ROOT_PATH)
elif 'fr' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_fr.yaml'.format(ROOT_PATH)
elif 'de' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_de.yaml'.format(ROOT_PATH)
elif 'es' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_es.yaml'.format(ROOT_PATH)
elif 'nl' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_nl.yaml'.format(ROOT_PATH)
elif 'sv' in configuration['Language']['Choice']:
    keywordfile= '{}/src/keywords_sv.yaml'.format(ROOT_PATH)
else:
    keywordfile= '{}/src/keywords_en.yaml'.format(ROOT_PATH)
with open(keywordfile,'r' , encoding='utf8') as conf:
    custom_action_keyword = yaml.load(conf)

#Sonoff-Tasmota Declarations
#Make sure that the device name assigned here does not overlap any of your smart device names in the google home app
tasmota_devicelist=configuration['Tasmota_devicelist']['friendly-names']
tasmota_deviceip=configuration['Tasmota_devicelist']['ipaddresses']
tasmota_deviceportid=configuration['Tasmota_devicelist']['portID']


#Domoticz Declarations
domoticz_devices=''
Domoticz_Device_Control=False
bright=''
hexcolour=''
# Get devices list from domoticz server
if configuration['Domoticz']['Domoticz_Control']=='Enabled':
    Domoticz_Device_Control=True
    try:
        domoticz_response = requests.get("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=devices&filter=all&order=Name",verify=False)
        domoticz_devices=json.loads(domoticz_response.text)
        with open('{}/domoticz_device_list.json'.format(USER_PATH), 'w') as devlist:
            json.dump(domoticz_devices, devlist)
    except requests.exceptions.ConnectionError:
        print("Domoticz server not online")
else:
    Domoticz_Device_Control=False

#ESP device declarations
ip=configuration['ESP']['IP']
devname=configuration['ESP']['devicename']
devid=configuration['ESP']['deviceid']

#Initialize colour list
clrlist=[]
clrlistfullname=[]
clrrgblist=[]
clrhexlist=[]
with open('{}/src/colours.json'.format(ROOT_PATH), 'r') as col:
     colours = json.load(col)
for i in range(0,len(colours)):
    clrname=colours[i]["name"]
    clrnameshort=clrname.replace(" ","",1)
    clrnameshort=clrnameshort.strip()
    clrnameshort=clrnameshort.lower()
    clrlist.append(clrnameshort)
    clrlistfullname.append(clrname)
    clrrgblist.append(colours[i]["rgb"])
    clrhexlist.append(colours[i]["hex"])


class HomeAutomationHub():

    def __init__(self):
        if configuration['MQTT']['MQTT_Control']=='Enabled':
            self.t1 = Thread(target=self.mqtt_start)
            self.t1.start()
        if configuration['ADAFRUIT_IO']['ADAFRUIT_IO_CONTROL']=='Enabled':
            self.t2 = Thread(target=self.adafruit_mqtt_start)
            self.t2.start()

    #Function to get HEX and RGB values for requested colour
    def getcolours(self,command):
        usrclridx=idx=command.find(custom_action_keyword['Dict']['To'])
        usrclr=query=command[usrclridx:]
        usrclr=usrclr.replace(custom_action_keyword['Dict']['To'],"",1)
        usrclr=usrclr.strip()
        usrclr=usrclr.lower()
        print(usrclr)
        try:
            for colournum, colourname in enumerate(clrlist):
                if usrclr in colourname:
                   RGB=clrrgblist[colournum]
                   red,blue,green=re.findall('\d+', RGB)
                   hexcode=clrhexlist[colournum]
                   cname=clrlistfullname[colournum]
                   print(cname)
                   break
            return red,blue,green,hexcode,cname
        except UnboundLocalError:
            print("Sorry unable to find a matching colour")

    #Function to convert FBG to XY for Hue Lights
    def convert_rgb_xy(self,red,green,blue):
        try:
            red = pow((red + 0.055) / (1.0 + 0.055), 2.4) if red > 0.04045 else red / 12.92
            green = pow((green + 0.055) / (1.0 + 0.055), 2.4) if green > 0.04045 else green / 12.92
            blue = pow((blue + 0.055) / (1.0 + 0.055), 2.4) if blue > 0.04045 else blue / 12.92
            X = red * 0.664511 + green * 0.154324 + blue * 0.162028
            Y = red * 0.283881 + green * 0.668433 + blue * 0.047685
            Z = red * 0.000088 + green * 0.072310 + blue * 0.986039
            x = X / (X + Y + Z)
            y = Y / (X + Y + Z)
            return x,y
        except UnboundLocalError:
            print("No RGB values given")

    #ESP6266 Devcies control
    def ESP(self,command):
        try:
            for num, name in enumerate(devname):
                if name.lower() in command:
                    dev=devid[num]
                    if custom_action_keyword['Dict']['On'] in command:
                        ctrl='=ON'
                        print("Turning On " + name)
                    elif custom_action_keyword['Dict']['Off'] in command:
                        ctrl='=OFF'
                        print("Turning Off " + name)
                    rq = requests.head("http://"+ip + dev + ctrl)
        except requests.exceptions.ConnectionError:
            print("Device not online")

    #Function to control Sonoff Tasmota Devices
    def tasmota_control(self,command,devname,devip,devportid):
        try:
            if custom_action_keyword['Dict']['On'] in command:
                rq=requests.head("http://"+devip+"/cm?cmnd=Power"+devportid+"%20on")
                print("Tunring on "+devname)
            elif custom_action_keyword['Dict']['Off'] in command:
                rq=requests.head("http://"+devip+"/cm?cmnd=Power"+devportid+"%20off")
                print("Tunring off "+devname)
        except requests.exceptions.ConnectionError:
            print("Device not online")

    #Function to control DIY HUE
    def hue_control(self,phrase,lightindex,lightaddress):
        with open('/opt/hue-emulator/config.json', 'r') as config:
             hueconfig = json.load(config)
        currentxval=hueconfig['lights'][lightindex]['state']['xy'][0]
        currentyval=hueconfig['lights'][lightindex]['state']['xy'][1]
        currentbri=hueconfig['lights'][lightindex]['state']['bri']
        currentct=hueconfig['lights'][lightindex]['state']['ct']
        huelightname=str(hueconfig['lights'][lightindex]['name'])
        try:
            if custom_action_keyword['Dict']['On'] in phrase:
                huereq=requests.head("http://"+lightaddress+"/set?light="+lightindex+"&on=true")
                print("Turning on "+huelightname)
            if custom_action_keyword['Dict']['Off'] in phrase:
                huereq=requests.head("http://"+lightaddress+"/set?light="+lightindex+"&on=false")
                print("Turning off "+huelightname)
            if 'çolor' in phrase:
                rcolour,gcolour,bcolour,hexcolour,colour=getcolours(phrase)
                print(str([rcolour,gcolour,bcolour,hexcolour,colour]))
                xval,yval=convert_rgb_xy(int(rcolour),int(gcolour),int(bcolour))
                print(str([xval,yval]))
                huereq=requests.head("http://"+lightaddress+"/set?light="+lightindex+"&x="+str(xval)+"&y="+str(yval)+"&on=true")
                print("http://"+lightaddress+"/set?light="+lightindex+"&x="+str(xval)+"&y="+str(yval)+"&on=true")
                print("Setting "+huelightname+" to "+colour)
            if (custom_action_keyword['Dict']['Brightness']).lower() in phrase:
                if 'hundred'.lower() in phrase or custom_action_keyword['Dict']['Maximum'] in phrase:
                    bright=100
                elif 'zero'.lower() in phrase or custom_action_keyword['Dict']['Minimum'] in phrase:
                    bright=0
                else:
                    bright=re.findall('\d+', phrase)
                brightval= (bright/100)*255
                huereq=requests.head("http://"+lightaddress+"/set?light="+lightindex+"&on=true&bri="+str(brightval))
                print("Changing "+huelightname+" brightness to "+bright+" percent")
        except (requests.exceptions.ConnectionError,TypeError) as errors:
            if str(errors)=="'NoneType' object is not iterable":
                print("Type Error")
            else:
                print("Device not online")

   #Function to control Domoticz Devices
    def domoticz_control(self,query,index,devicename):
        global hexcolour,bright,devorder
        try:
            for j in range(0,len(domoticz_devices['result'])):
                if domoticz_devices['result'][j]['idx']==index:
                    devorder=j
                    break
            if (' ' + custom_action_keyword['Dict']['On'] + ' ') in query or (' ' + custom_action_keyword['Dict']['On']) in query or (custom_action_keyword['Dict']['On'] + ' ') in query:
                devreq=requests.head("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=command&param=switchlight&idx=" + index + "&switchcmd=On",verify=False)
                print('Turning on ' + devicename )
            if custom_action_keyword['Dict']['Off'] in query:
                devreq=requests.head("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=command&param=switchlight&idx=" + index + "&switchcmd=Off",verify=False)
                print('Turning off ' + devicename )
            if 'toggle' in query:
                devreq=requests.head("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=command&param=switchlight&idx=" + index + "&switchcmd=Toggle",verify=False)
                print('Toggling ' + devicename )
            if custom_action_keyword['Dict']['Colour'] in query:
                if 'RGB' in domoticz_devices['result'][devorder]['SubType']:
                    rcolour,gcolour,bcolour,hexcolour,colour=getcolours(query)
                    hexcolour=hexcolour.replace("#","",1)
                    hexcolour=hexcolour.strip()
                    print(hexcolour)
                    if bright=='':
                        bright=str(domoticz_devices['result'][devorder]['Level'])
                    devreq=requests.head("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=command&param=setcolbrightnessvalue&idx=" + index + "&hex=" + hexcolour + "&brightness=" + bright + "&iswhite=false",verify=False)
                    print('Setting ' + devicename + ' to ' + colour )
                else:
                    print('The requested light is not a colour bulb')
            if custom_action_keyword['Dict']['Brightness'] in query:
                if domoticz_devices['result'][devorder]['HaveDimmer']:
                    if 'hundred' in query or 'hundred'.lower() in query or custom_action_keyword['Dict']['Maximum'] in query:
                        bright=str(100)
                    elif 'zero' in query or custom_action_keyword['Dict']['Minimum'] in query:
                        bright=str(0)
                    else:
                        bright=re.findall('\d+', query)
                        bright=bright[0]
                    devreq=requests.head("https://" + configuration['Domoticz']['Server_IP'][0] + ":" + configuration['Domoticz']['Server_port'][0] + "/json.htm?type=command&param=switchlight&idx=" + index + "&switchcmd=Set%20Level&level=" + bright ,verify=False)
                    print('Setting ' + devicename + ' brightness to ' + str(bright) + ' percent.')
                else:
                    print('The requested light does not have a dimer')

        except (requests.exceptions.ConnectionError,TypeError) as errors:
            if str(errors)=="'NoneType' object is not iterable":
                print("Type Error")
            else:
                print("Device or Domoticz server is not online")

    def on_connect(self, client, userdata, flags, rc):
        print("Connected with result code "+str(rc))
        client.subscribe(configuration['MQTT']['TOPIC'])

    def on_message(self, client, userdata, msg):
        print("Message from MQTT: "+str(msg.payload.decode('utf-8')))
        mqtt_query=str(msg.payload.decode('utf-8'))
        self.custom_command(mqtt_query)            

    def mqtt_start(self):
        client = mqtt.Client()
        client.on_connect = self.on_connect
        client.on_message = self.on_message
        client.username_pw_set(configuration['MQTT']['UNAME'], configuration['MQTT']['PSWRD'])
        client.connect(configuration['MQTT']['IP'], 1883, 60)
        client.loop_forever()

    def adafruit_connected(self,client):
        print('Connected to Adafruit IO!  Listening for DemoFeed changes...')
        client.subscribe(configuration['ADAFRUIT_IO']['FEEDNAME'])

    def adafruit_disconnected(self,client):
        print('Disconnected from Adafruit IO!')

    def adafruit_message(self,client, feed_id, payload):
        if self.can_start_conversation == True:
            print("Message from ADAFRUIT MQTT: "+str(payload.decode('utf-8')))
            adafruit_mqtt_query=str(payload.decode('utf-8'))
            self.custom_command(adafruit_mqtt_query)

    def adafruit_mqtt_start(self):
        if configuration['ADAFRUIT_IO']['ADAFRUIT_IO_CONTROL']=='Enabled':
            client = MQTTClient(configuration['ADAFRUIT_IO']['ADAFRUIT_IO_USERNAME'], configuration['ADAFRUIT_IO']['ADAFRUIT_IO_KEY'])
            client.on_connect    = self.adafruit_connected
            client.on_disconnect = self.adafruit_disconnected
            client.on_message    = self.adafruit_message
            client.connect()
            client.loop_background()
        else:
            print("Adafruit_io MQTT client not enabled")

    def custom_command(self,command):
        if configuration['DIYHUE']['DIYHUE_Control']=='Enabled':
            if os.path.isfile('/opt/hue-emulator/config.json'):
                with open('/opt/hue-emulator/config.json', 'r') as config:
                     hueconfig = json.load(config)
                for i in range(1,len(hueconfig['lights'])+1):
                    try:
                        if str(hueconfig['lights'][str(i)]['name']).lower() in str(command).lower():
                            self.hue_control(str(command).lower(),str(i),str(hueconfig['lights_address'][str(i)]['ip']))
                            break
                    except Keyerror:
                        print('Unable to help, please check your config file')

        if configuration['Tasmota_devicelist']['Tasmota_Control']=='Enabled':
            for num, name in enumerate(tasmota_devicelist):
                if name.lower() in str(command).lower():

                    tasmota_control(str(command).lower(), name.lower(),tasmota_deviceip[num],tasmota_deviceportid[num])
                    break

        if Domoticz_Device_Control==True and len(domoticz_devices['result'])>0:
            if len(configuration['Domoticz']['Devices']['Name'])==len(configuration['Domoticz']['Devices']['Id']):
                for i in range(0,len(configuration['Domoticz']['Devices']['Name'])):
                    if str(configuration['Domoticz']['Devices']['Name'][i]).lower() in str(command).lower():
                        domoticz_control(str(command).lower(),configuration['Domoticz']['Devices']['Id'][i],configuration['Domoticz']['Devices']['Name'][i])
                        break
            else:
                print("Number of devices and the number of ids given in config file do not match")

         if configuration['ESP']['ESP_Control']=='Enabled':
            if (custom_action_keyword['Keywords']['ESP_control'][0]).lower() in str(command).lower():
                ESP(str(command).lower())

if __name__ == '__main__':
    print("Running the HUB......")
