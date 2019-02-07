# HomeAutomationHub
Using Adafruit IO or Local MQTT control devices like Sonoff-Tasmota, Domoticz, Emulated Wemo etc.     

## Steps to get started:    
1. Clone the Git    

```
cd /home/${USER}    
sudo apt-get install git     
git clone https://github.com/shivasiddharth/HomeAutomationHub    
```

2. Install the dependencies     

```    
sudo chmod +x /home/${USER}/HomeAutomationHub/scripts/installer.sh    
sudo /home/${USER}/HomeAutomationHub/scripts/installer.sh    
```    

3. Install the service installer      

```    
sudo chmod +x /home/${USER}/HomeAutomationHub/scripts/service-installer.sh   
sudo /home/${USER}/HomeAutomationHub/scripts/service-installer.sh      
```     

4. Enter the credentials or device info in the config.yaml file.      

5. Set the service to start on boot        
```     
sudo systemctl enable homeautomationhub.service     
sudo systemctl start homeautomationhub.service      
```       

## Devices that currently work:   
 - Sonoff-Tasmota   
 - Domoticz Devices    
 - Emulated Wemo   

## Devices to be added/fixed:   
 - diyHue   
