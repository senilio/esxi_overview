#!/usr/bin/env python

# ESXi stats. New version using pyvmomi
# 2017-01-30 / senilio

from __future__ import print_function
import os
import sys
import atexit
import ssl
import pchelper
import collections
import argparse
import ConfigParser

from datetime import datetime
from jinja2 import Environment, Template, FileSystemLoader
from pyVim import connect
from pyVmomi import vim

def main():

    # Parse path to configuration file
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', help='Configuration ini file.', required=True)
    args = parser.parse_args()

    # Parse the config file
    config = ConfigParser.ConfigParser()
    config.read(args.c)
    if not config.sections():
        print("Unable to read configuration file.")
        sys.exit()

    service_instance = None
    try:
        context = ssl.SSLContext(ssl.PROTOCOL_SSLv23)
        context.verify_mode = ssl.CERT_NONE

        service_instance = connect.SmartConnect(
            host=config.get('main', 'Server'),
            user=config.get('main', 'Username'),
            pwd=config.get('main', 'Password'),
            port=443,sslContext=context)

        atexit.register(connect.Disconnect, service_instance)
    except IOError as e:
        pass

    if not service_instance:
        raise SystemExit("Unable to connect to host with supplied info.")

    # Get current time
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S (%Z)')

    # VM properties to fetch
    vm_properties = ["name",
                     "guest.hostName",
                     "config.guestFullName",
                     "summary.quickStats.overallCpuUsage",
                     "summary.quickStats.uptimeSeconds",
                     "summary.customValue",
                     "summary.quickStats",
                     "config.hardware.memoryMB",
                     "config.hardware.numCPU",
                     "config.hardware.device",
                     "config.annotation",
                     "summary.runtime.powerState",
                     "runtime.host",
                     "network",
                     "guest.toolsRunningStatus",
                     "guest.toolsVersionStatus",
                     "guest.net",
                     "guest.guestState",
                     "config.guestId",
                     "config.version"]

    # Host properties to fetch
    host_properties = ["config.product.fullName",
                      "hardware.cpuInfo.numCpuCores",
                      "hardware.cpuInfo.hz",
                      "hardware.cpuInfo.numCpuThreads",
                      "hardware.cpuInfo.numCpuPackages",
                      "hardware.memorySize",
                      "hardware.systemInfo.model",
                      "hardware.systemInfo.vendor",
                      "hardware.biosInfo.biosVersion",
                      "name",
                      "summary.hardware.cpuModel",
                      "summary.hardware.numCpuPkgs",
                      "summary.hardware.numNics",
                      "summary.overallStatus"]

    root_folder = service_instance.content.rootFolder

    vm_view = pchelper.get_container_view(service_instance,
                                       obj_type=[vim.VirtualMachine])
    vm_data = pchelper.collect_properties(service_instance, view_ref=vm_view,
                                          obj_type=vim.VirtualMachine,
                                          path_set=vm_properties,
                                          include_mors=True)

    host_view = pchelper.get_container_view(service_instance,
                                       obj_type=[vim.HostSystem])
    host_data = pchelper.collect_properties(service_instance, view_ref=host_view,
                                          obj_type=vim.HostSystem,
                                          path_set=host_properties,
                                          include_mors=True)

    # Return dictionary of network info
    def get_network_info(guest_net):
        networking = {}
        for nic in guest_net:
            networking['vlan'] = []
            networking['mac']  = []
            networking['ip']   = []

            if nic.ipAddress:
                for i in nic.ipAddress:
                    if not ':' in i:
                        networking['ip'].append(i)

            if nic.network:
                networking['vlan'].append(nic.network)

            if nic.macAddress:
                networking['mac'].append(nic.macAddress)

		return(networking)


    # Return human readable uptime
    def return_uptime(seconds):
		days = seconds / 86400
		seconds -= 86400 * days
		hrs = seconds / 3600
		seconds -= 3600 * hrs
		mins = seconds / 60
		seconds -= 60 * mins
		if days >= 7:
			return '{} days'.format(days)
		elif days >= 1 and days < 7:
			return '{}d {}h'.format(days, hrs)
		else:
			return '{}h {}m'.format(hrs, mins)

    # Return human readable mem size
    def memGB(MB):
		if MB > 1000:
			return MB/1024
		elif MB < 1001:
			return '.{}'.format(str(MB)[:1])
		else:
			return '-'

    # Host ID to hostname translation dictionary
    host_to_hostname = {}
    for host in host_data:
        host_to_hostname[host['obj']] = host['name']

    # Init dictionary of VMs
    vms = {}

    # Populate vms dictionary
    for vm in vm_data:
        vms[vm["name"]] = {}
        vms[vm["name"]]['numCPU']        = vm["config.hardware.numCPU"]
        vms[vm["name"]]['memoryMB']      = vm["config.hardware.memoryMB"]
        vms[vm["name"]]['host']          = host_to_hostname[vm["runtime.host"]]
        vms[vm["name"]]['powerState']    = vm["summary.runtime.powerState"]
        vms[vm["name"]]['guestState']    = vm["guest.guestState"]
        vms[vm["name"]]['ballooning']    = vm["summary.quickStats"].balloonedMemory
        vms[vm["name"]]['swapping']      = vm["summary.quickStats"].swappedMemory
        vms[vm["name"]]['guestName']     = vm["config.guestFullName"]
        vms[vm["name"]]['hwVersion']     = vm["config.version"]
        vms[vm["name"]]['annotation']    = vm[u"config.annotation"]
        vms[vm["name"]]['uptime']        = return_uptime(vm["summary.quickStats"].uptimeSeconds)
        vms[vm["name"]]['toolsVersion']  = vm["guest.toolsVersionStatus"]
        vms[vm["name"]]['toolsRunning']  = vm["guest.toolsRunningStatus"]
        vms[vm["name"]]['cpuUsage']      = vm["summary.quickStats"].overallCpuUsage
        vms[vm["name"]]['networking']    = get_network_info(vm['guest.net'])
        vms[vm["name"]]['disks']         = {}

        for device in vm['config.hardware.device']:
            if type(device).__name__ == 'vim.vm.device.VirtualDisk':
                vms[vm["name"]]['disks'][device.deviceInfo.label] = {
                       'size' : device.capacityInKB / 1024 / 1024,
                       'file' : device.backing.fileName}
                try:
                    if thinProvisioned in device.backing:
                        vms[vm["name"]]['disks'][device.deviceInfo.label] = {
                            'thin' : str(device.backing.thinProvisioned)}
                except:
                    vms[vm["name"]]['disks'][device.deviceInfo.label] = {
                        'thin' : 'false'}

    # Init dictionary of hosts
    hosts = {}

    # Populate host dictionary
    for host in host_data:
        hosts[host["name"]] = {}
        hosts[host["name"]]["fullName"]         = host["config.product.fullName"]
        hosts[host["name"]]["numCores"]         = host["hardware.cpuInfo.numCpuCores"]
        hosts[host["name"]]["cpuHz"]            = host["hardware.cpuInfo.hz"]
        hosts[host["name"]]["cpuMHz"]           = int(host["hardware.cpuInfo.hz"]) / 1000000 + 1
        hosts[host["name"]]["cpuThreads"]       = host["hardware.cpuInfo.numCpuThreads"]
        hosts[host["name"]]["cpuCount"]         = host["hardware.cpuInfo.numCpuPackages"]
        hosts[host["name"]]["cpuModel"]         = host["summary.hardware.cpuModel"]
        hosts[host["name"]]["memSize"]          = host["hardware.memorySize"] / 1024 / 1024 / 1023
        hosts[host["name"]]["model"]            = host["hardware.systemInfo.model"]
        hosts[host["name"]]["vendor"]           = host["hardware.systemInfo.vendor"]
        hosts[host["name"]]["biosVersion"]      = host["hardware.biosInfo.biosVersion"]
        hosts[host["name"]]["numCpuPkgs"]       = host["summary.hardware.numCpuPkgs"]
        hosts[host["name"]]["numNics"]          = host["summary.hardware.numNics"]
        hosts[host["name"]]["health"]           = host["summary.overallStatus"]

    # Calculate extra parameters to avoid doing too many calculations in template
    for host in hosts:
        memoryUsage = 0
        vcpuUsage = 0
        runningVMs = 0
        for vm in vms:
            if vms[vm]['host'] == host and vms[vm]['powerState'] == 'poweredOn':
                memoryUsage += vms[vm]['memoryMB']
                vcpuUsage += vms[vm]['numCPU']
                vms[vm]['memoryGB'] = memGB(vms[vm]['memoryMB'])
            if vms[vm]['host'] == host and vms[vm]['powerState'] == 'poweredOn':
                runningVMs += 1

        hosts[host]['memoryUsage']              = memoryUsage / 1024
        hosts[host]['cpuUsage']                 = vcpuUsage
        hosts[host]['runningVMs']               = runningVMs
        hosts[host]['memoryUsagePercentage']    = int(float(hosts[host]['memoryUsage']) /
                                                    float(hosts[host]['memSize']) * 100)
        hosts[host]['cpuUsagePercentage']       = int(float(hosts[host]['cpuUsage']) /
                                                    float(hosts[host]['numCores']) * 100)

    # Shift historic files, keep number of versions defined in ini file
    for i in range(int(config.get('main', 'History')), 1, -1):
        try:
            os.rename('{}/{}.html'.format(config.get('main', 'OutputPath'), i-1),
                      '{}/{}.html'.format(config.get('main', 'OutputPath'), i))
        except OSError:
            pass

    try:
        os.rename('{}/{}'.format(config.get('main', 'OutputPath'), config.get('main', 'OutputFile')),
                  '{}/1.html'.format(config.get('main', 'OutputPath')))
    except OSError:
        pass

    ### Start generating HTML

    # Capture our current directory
    THIS_DIR = os.path.dirname(os.path.abspath(__file__))

    j2_env = Environment(loader=FileSystemLoader(THIS_DIR),
                         trim_blocks=True,
                         lstrip_blocks=True )

    file = open(config.get('main', 'OutputPath')+
                '/'+
                config.get('main', 'OutputFile'),'w')

    file.write(j2_env.get_template(config.get('main', 'Template')).render(
        title=config.get('main', 'Site') + ' ESXi overview',
        last_update=current_time,
        vms=collections.OrderedDict(sorted(vms.items())),
        hosts=collections.OrderedDict(sorted(hosts.items())),
        filename=config.get('main', 'OutputFile'),
        instances=int(config.get('main', 'History')))
    )

    file.close()

# Start program
if __name__ == "__main__":
    main()
