from netbrain.sysapi import datamodel 
from netbrain.sysapi import devicedata 
from netbrain.sysapi import pluginfw 
from netbrain.sysapi import oneiptable
import pynetbox
import re
import json

cidr_regex = re.compile(r'^.*\/(\d{2})$')

def run(input): 
    ''' 
        this is the plugin entry point. 
        todo: write the real logic in this function. 
        
        return True if the everything is OK. 
        return False if some error occurred. 
        
    ''' 
    
    # Parse plugin input
    input_json = json.loads(input)
    end_point = input_json["end_point"]
    token = input_json["token"]
    default_mask = input_json["default_mask"]
    device_group = input_json["device_group"]
    default_site = input_json["default_site"]
    
    
    nb = pynetbox.api(
        end_point,
        token=token,
    )
    nb.http_session.verify = False
    
    device_list = datamodel.GetDeviceIdsFromDeviceGroup(device_group)
    
    for device in device_list:
        pluginfw.AddLog(f"---------")
        dev_obj = datamodel.GetDeviceObjectById(device)
        devicename = dev_obj["name"]
        #pluginfw.AddLog(str(dev_obj), pluginfw.DEBUG) # Print all device details for debugging
        pluginfw.AddLog(f"{devicename} started, adding dependencies")
        
        # Populate device details from NetBrain device object
        mgmtIP = dev_obj["mgmtIP"]
        mgmtIntf = dev_obj["mgmtIntf"]
        vendor = dev_obj["vendor"]
        subTypeName = dev_obj["subTypeName"]
        siteName = datamodel.GetDeviceSiteName(devicename)
        location = datamodel.GetDeviceProperty("loc", devicename)
        mainTypeName = dev_obj["mainTypeName"]
        model = dev_obj["model"]
        
        # Set site for unassigned devices
        if len(siteName) == 0:
            siteName = default_site
  
        # Create slugs
        vendorSlug = vendor.replace(" ", "_")
        subTypeNameSlug = subTypeName.replace(" ", "_")
        mainTypeNameSlug = mainTypeName.replace(" ", "_")
        siteNameSlug = siteName.replace(" ", "_")
 
        # Get Management IP with Mask
        mgmtIP_details = oneiptable.GetOneIpTableItem(mgmtIP)
        if len(mgmtIP_details) > 0:
            mask_search = re.search(cidr_regex, mgmtIP_details[0]["lanSegment"])
            if mask_search:
                mgmtCIDR = mask_search.group(1)
        else:
            mgmtCIDR = default_mask
            
        mgmtIPcidr = f"{mgmtIP}/{mgmtCIDR}"
        #pluginfw.AddLog(f"MgmtIP details: {mgmtIPcidr}", pluginfw.DEBUG)
        
        # Add device logic
        if nb.dcim.devices.get(devicename) is None:
            # Add dependencies for devices: role, vendor, device type, site
            # Check if role exists
            if nb.dcim.device_roles.get(slug=mainTypeNameSlug) is None:
                try:
                    nb.dcim.device_roles.create(
                        name=mainTypeName,
                        slug=mainTypeNameSlug
                    )
                    pluginfw.AddLog(f"Role {mainTypeName} added in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Role {mainTypeName} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"Role {mainTypeName} already exists")
            # check if Vendor exists
            if nb.dcim.manufacturers.get(slug=vendorSlug) is None:
                try:
                    nb.dcim.manufacturers.create(
                        name=vendor,
                        slug=vendorSlug
                    )
                    pluginfw.AddLog(f"Manufacturer {vendor} added in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Manufacturer {vendor} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"Manufacturer {vendor} already exists")
            # Check if device type exists
            if nb.dcim.device_types.get(slug=subTypeNameSlug) is None:
                try:
                    nb.dcim.device_types.create(
                        name=subTypeName,
                        manufacturer=nb.dcim.manufacturers.get(slug=vendorSlug).id,
                        model=model,
                        slug=subTypeNameSlug
                    )
                    pluginfw.AddLog(f"Device Type {subTypeName} added in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Device Type {subTypeName} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"Device Type {subTypeName} already exists")
          
            # check if site exists
            pluginfw.AddLog(f"Adding site {siteName} with slug {siteNameSlug}")
            if nb.dcim.sites.get(slug=siteNameSlug) is None:
                try:
                    nb.dcim.sites.create(
                        name=siteName,
                        slug=siteNameSlug
                    )
                    pluginfw.AddLog(f"Site {siteName} added in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Site {siteName} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"Site {siteName} already exists")
                
            # check if mgmtIP exists
            
            if nb.ipam.ip_addresses.get(address=mgmtIPcidr) is None:
                try:
                    nb.ipam.ip_addresses.create(
                        address=mgmtIPcidr
                    )
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"IP Address {mgmtIPcidr} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"IP Address {mgmtIPcidr} already exists")
            
            # Add Device to NetBox
            if nb.dcim.devices.get(name=devicename) is None:
                try:
                    netbox_dev = nb.dcim.devices.create(
                        name = devicename,
                        device_type = nb.dcim.device_types.get(slug=subTypeNameSlug).id,
                        role = nb.dcim.device_roles.get(slug=mainTypeNameSlug).id,
                        site = nb.dcim.sites.get(slug=siteNameSlug).id,
                        manufacturer = nb.dcim.manufacturers.get(slug=vendorSlug).id,
                        status = "active"
                    )
                    pluginfw.AddLog(f"Device {devicename} added in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Device {devicename} failed to added in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            else:
                pluginfw.AddLog(f"Device {devicename} already exists")
        
        
            # Get Device Interfaces and check if management interface exists
        
            dev_intfs = datamodel.GetInterfaceIdsByDeviceName(devicename, "intfs")

            # Loop through all interfaces on the device
            for intf in dev_intfs:
                intf_obj = datamodel.GetInterfaceObjectById(intf["interface id"], intf["interface type"])

                # Check if the interface is the management interface
                if intf_obj["name"] == dev_obj["mgmtIntf"]:
                    # Create Device Interface for the management interface
                    if nb.dcim.interfaces.get(name=dev_obj["mgmtIntf"], device_id=nb.dcim.devices.get(name=devicename).id) is None:
                        try:
                            netbox_intf = nb.dcim.interfaces.create(
                                name = intf_obj["name"],
                                device = nb.dcim.devices.get(name=devicename).id,
                                type = "other",
                                description = intf_obj["descr"]
                            )
                            pluginfw.AddLog(f"Interface {devicename}.{intf_obj["name"]} added in NetBox")
                        except pynetbox.RequestError as e:
                            pluginfw.AddLog(f"Interface {devicename}.{intf_obj["name"]} failed to add in NetBox", pluginfw.ERROR)
                            pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                    # Check if management IP is assigned to management interface    
                    if nb.ipam.ip_addresses.get(address=mgmtIPcidr).assigned_object is None:
                        # Assign IP Address to Interface
                        pluginfw.AddLog(f"Assign address to interface ip:{mgmtIPcidr} device:{devicename} interface:{mgmtIntf}", pluginfw.INFO)
                        add_obj = nb.ipam.ip_addresses.get(address=mgmtIPcidr)
                        add_obj.assigned_object_type = "dcim.interface"
                        add_obj.assigned_object = nb.dcim.interfaces.get(name=dev_obj["mgmtIntf"], device_id=nb.dcim.devices.get(name=devicename).id)
                        add_obj.assigned_object_id = nb.dcim.interfaces.get(name=dev_obj["mgmtIntf"], device_id=nb.dcim.devices.get(name=devicename).id).id
                        
                        try:
                            update_address = nb.ipam.ip_addresses.update(
                                [add_obj]    
                            )
                            pluginfw.AddLog(f"Associated {devicename}.{intf_obj["name"]} to {add_obj["address"]} in NetBox")
                        except pynetbox.RequestError as e:
                            pluginfw.AddLog(f"Associated {devicename}.{intf_obj["name"]} to {add_obj["address"]} failed in NetBox", pluginfw.ERROR)
                            pluginfw.AddLog(str(e.error), pluginfw.ERROR)
            
            # Update management IP on device
            nb_devobj = nb.dcim.devices.get(name=devicename)
            if nb_devobj.primary_ip4 is None:
                nb_devobj.primary_ip4 = nb.ipam.ip_addresses.get(address=mgmtIPcidr).id
                try:
                    netbox_dev = nb.dcim.devices.update(
                        [nb_devobj]
                    )
                    pluginfw.AddLog(f"Device {devicename} updated with management IP in NetBox")
                except pynetbox.RequestError as e:
                    pluginfw.AddLog(f"Device {devicename} failed to update management IP in NetBox", pluginfw.ERROR)
                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)

        #device_config = devicedata.GetConfig(device_name)
        
        #pluginfw.AddLog(str(device_config), pluginfw.INFO)

    
    return True
