# ESXi overview
 
### What's this?
This script polls your vCenter server for a bunch of information, which is gathers in a huge dictionary. The information in the dictionary are then used as a
 base for Jinja2 to generate a HTML page with details of your ESXi host(s)/cluster.

### Why?
I wanted anyone in our company to be able to see host allocation, virtual machines, ip addresses, VLAN, OS versions, VM CPU and RAM allocation of all of our clusters... without having to give them accounts. So what better way than to present the info in a simple HTML page?

### Usage
First of all, clone the repo. Put it somewhere like /usr/local. Fetch all dependencies listed at the top of the script.

The first thing you need to do is to create an ini file with information about your vCenter server:

```
[main]
# Server to connect to
Server: vcenter-fqdn-or-ip

# Credentials
Username: username
Password: password

# Name to prepend in the HTML title
Site: Sitename

# Path to store html files
OutputPath: /var/www/html/vmware/Sitename

# Filename to output to
OutputFile: index.html

# Jinja2 template file to use
Template: esxi_overview.template

# Number of historical files to keep and link to
History: 47

```

Store the ini files somewhere safe and fix permissions, since they contain information on how to log in to your vCenter server.

```
mkdir /usr/local/esxi_overview/site_config
chmod 600 /usr/local/esxi_overview/site_config
vi /usr/local/esxi_overview/site_config/site.ini
chmod 600 /usr/local/esxi_overview/site_config/site.ini
```

Test run the script like this:
```
cd /usr/local/esxi_overview && python esxi_overview.py -c site_config/site.ini
```

Run the script from crontab like this:

```
0 * * * * cd /usr/local/esxi_overview && python esxi_overview.py -c site_config/se1.ini
```

I run the script once per hour, which means that I will have a history of 48 hours kept in my output path.

### Have fun
Feel free to create your own Jinja2 template files and share them back with me. As you can see in the included template, HTML design isn't my strongest suit :)
