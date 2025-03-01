from netbrain.sysapi import datamodel 
from netbrain.sysapi import devicedata 
from netbrain.sysapi import pluginfw 
from netbrain.sysapi import oneiptable
import re
import json
import socket

try:
    import pynetbox
except ImportError as e:
    pluginfw.AddLog(f"Failed to import pynetbox module on {socket.gethostname()}", pluginfw.ERROR)
    pluginfw.AddLog(str(e.error), pluginfw.ERROR)

cidr_regex = re.compile(r'^.*\/(\d{2})$')
f5_serial_regex = re.compile(r'^Serial:\s(.+)\sMAC')

def run(input): 
    # Parse plugin input
    input_json = json.loads(input)
    end_point = input_json["end_point"]
    token = input_json["token"]
    default_mask = input_json["default_mask"]
    device_group = input_json["device_group"]
    default_site = input_json["default_site"]
    
    # Connect to Netbox
    nb = pynetbox.api(
        end_point,
        token=token,
    )
    nb.http_session.verify = False
    
    # Get list of devices from input device group
    device_list = datamodel.GetDeviceIdsFromDeviceGroup(device_group)
    
    for device in device_list:
        pluginfw.AddLog(f"---------")
        dev_obj = datamodel.GetDeviceObjectById(device)
        devicename = dev_obj["name"]
        pluginfw.AddLog(str(dev_obj), pluginfw.DEBUG) # Print all device details for debugging
        pluginfw.AddLog(f"{devicename} started, adding dependencies")
        
        # Populate device details from NetBrain device object, if not found, set to none
        mgmtIP = dev_obj["mgmtIP"] if dev_obj.get("mgmtIP") else None
        mgmtIntf = dev_obj["mgmtIntf"] if dev_obj.get("mgmtIntf") else None
        vendor = dev_obj["vendor"] if dev_obj.get("vendor") else None
        subTypeName = dev_obj["subTypeName"] if dev_obj.get("subTypeName") else None
        siteName = datamodel.GetDeviceSiteName(devicename)
        mainTypeName = dev_obj["mainTypeName"] if dev_obj.get("mainTypeName") else None
        model = dev_obj["model"] if dev_obj.get("model") else None
        software_version = dev_obj["ver"] if dev_obj.get("ver") else None
        
        # Set site for unassigned devices
        if len(siteName) == 0:
            siteName = default_site
            
        # Get Serial
        serialNumber = dev_obj["sn"] if dev_obj.get("sn") else ""
        if vendor == "F5":
            serial_search = re.search(f5_serial_regex, serialNumber) # For F5's search for just the serial in the serial field
            if serial_search: 
                serialNumber = serial_search.group(1)
            else: # If serial number couldn't be found, truncate at 50 characters
                serialNumber = serialNumber[:50]
        elif len(serialNumber) > 50: # Find serials over 50 characters that aren't F5s and truncate them to 50 characters
            serialNumber = serialNumber[:50]

        # Check if any of the device properties are empty before creating the device
        if not [x for x in (mgmtIP, mgmtIntf, vendor, subTypeName, siteName, mainTypeName, model) if x is None]:
            
            # Create slugs
            vendorSlug = vendor.replace(" ", "_")
            subTypeNameSlug = subTypeName.replace(" ", "_")
            mainTypeNameSlug = mainTypeName.replace(" ", "_")
            siteNameSlug = siteName.replace(" ", "_")
            modelSlug = model.replace(" ", "_")
            swverSlug = software_version.replace(" ", "_").replace(".", "_").replace("(", "-").replace(")", "-") if software_version else None
    
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
                if nb.dcim.device_types.get(slug=modelSlug) is None:
                    try:
                        nb.dcim.device_types.create(
                            name=model,
                            manufacturer=nb.dcim.manufacturers.get(slug=vendorSlug).id,
                            model=model,
                            slug=modelSlug
                        )
                        pluginfw.AddLog(f"Device Type (Model) {model} added in NetBox")
                    except pynetbox.RequestError as e:
                        pluginfw.AddLog(f"Device Type (Model) {model} failed to added in NetBox", pluginfw.ERROR)
                        pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                else:
                    pluginfw.AddLog(f"Device Type (Model) {vendor} {model} already exists")
    
                # check if site exists
                #pluginfw.AddLog(f"Adding site {siteName} with slug {siteNameSlug}")
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
                    
                # Check if software version exists as platform    
                if software_version is not None:
                    if nb.dcim.platforms.get(slug=swverSlug) is None:
                        try:
                            nb.dcim.platforms.create(
                                name=software_version,
                                slug=swverSlug,
                                manufacturer = nb.dcim.manufacturers.get(slug=vendorSlug).id
                            )
                            pluginfw.AddLog(f"Platform {software_version} added in NetBox")
                        except pynetbox.RequestError as e:
                            pluginfw.AddLog(f"Platform {software_version} failed to added in NetBox", pluginfw.ERROR)
                            pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                    else:
                        pluginfw.AddLog(f"Platform {software_version} already exists")
                
                
                # check if mgmtIP exists
                if nb.ipam.ip_addresses.get(address=mgmtIP) is None:
                    try:
                        nb.ipam.ip_addresses.create(
                            address=mgmtIPcidr
                        )
                        pluginfw.AddLog(f"IP Address {mgmtIPcidr} added in NetBox")
                    except pynetbox.RequestError as e:
                        pluginfw.AddLog(f"IP Address {mgmtIPcidr} failed to added in NetBox", pluginfw.ERROR)
                        pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                elif str(nb.ipam.ip_addresses.get(address=mgmtIP)) != mgmtIPcidr:
                    # Update mgmt IP mask if it has changed
                    ip_addr_obj = nb.ipam.ip_addresses.get(address=mgmtIP)
                    old_ip_addr = ip_addr_obj.address
                    ip_addr_obj.address = mgmtIPcidr
                    try:
                        nb.ipam.ip_addresses.update(
                            [ip_addr_obj]
                        )
                        pluginfw.AddLog(f"IP Address {mgmtIPcidr} updated in NetBox, previously {old_ip_addr}")
                    except pynetbox.RequestError as e:
                        pluginfw.AddLog(f"IP Address {mgmtIPcidr} failed to update in NetBox", pluginfw.ERROR)
                        pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                else:
                    pluginfw.AddLog(f"IP Address {mgmtIPcidr} already exists")
                
                # Add Device to NetBox
                if nb.dcim.devices.get(name=devicename) is None:
                    try:
                        netbox_dev = nb.dcim.devices.create(
                            name = devicename,
                            device_type = nb.dcim.device_types.get(slug=model).id,
                            role = nb.dcim.device_roles.get(slug=mainTypeNameSlug).id,
                            site = nb.dcim.sites.get(slug=siteNameSlug).id,
                            manufacturer = nb.dcim.manufacturers.get(slug=vendorSlug).id,
                            serial = serialNumber,
                            platform = nb.dcim.platforms.get(slug=swverSlug).id if software_version else None,
                            status = "active"
                        )
                        if netbox_dev: # Validate that device was added to netbox by checking that netbox responded with the object
                            pluginfw.AddLog(f"Device {devicename} added in NetBox") 
                        else:
                            pluginfw.AddLog(f"Device {devicename} failed to added in NetBox", pluginfw.ERROR)
                    except pynetbox.RequestError as e:
                        pluginfw.AddLog(f"Device {devicename} failed to added in NetBox", pluginfw.ERROR)
                        pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                elif nb.dcim.devices.get(name=devicename): # Update already existing device in netbox
                    try:
                        netbox_devobj = nb.dcim.devices.get(name=devicename)
                        
                        # Update device properties
                        netbox_devobj.serial = serialNumber
                        netbox_devobj.device_type = nb.dcim.device_types.get(slug=modelSlug).id
                        netbox_devobj.site = nb.dcim.sites.get(slug=siteNameSlug).id
                        netbox_devobj.role = nb.dcim.device_roles.get(slug=mainTypeNameSlug).id
                        if software_version is not None:
                            netbox_devobj.platform = nb.dcim.platforms.get(slug=swverSlug).id
                        
                        # Send updated device to netbox
                        netbox_dev = nb.dcim.devices.update(
                            [netbox_devobj]    
                        )
                        pluginfw.AddLog(f"Device {devicename} updated in NetBox")
                    except pynetbox.RequestError as e:
                        pluginfw.AddLog(f"Device {devicename} failed to updated in NetBox", pluginfw.ERROR)
                        pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                else:
                    pluginfw.AddLog(f"Device {devicename} already exists")
                
            
                # Get Device Interfaces and check if management interface exists
                if nb.dcim.devices.get(name=devicename): # Only try adding management IP if the device exists
                    
                    # Get all device interfaces in NetBrain
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
                                    pluginfw.AddLog(f"Interface {devicename}.{intf_obj['name']} added in NetBox")
                                except pynetbox.RequestError as e:
                                    pluginfw.AddLog(f"Interface {devicename}.{intf_obj['name']} failed to add in NetBox", pluginfw.ERROR)
                                    pluginfw.AddLog(str(e.error), pluginfw.ERROR)
                            # Check if management IP is assigned to management interface    
                            if nb.ipam.ip_addresses.get(address=mgmtIP).assigned_object is None: # Check for IP address without CIDR to avoid not found issue if mask isn't updated
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
                                    pluginfw.AddLog(f"Associated {devicename}.{intf_obj['name']} to {add_obj['address']} in NetBox")
                                except pynetbox.RequestError as e:
                                    pluginfw.AddLog(f"Associating {devicename}.{intf_obj['name']} to {add_obj['address']} failed in NetBox", pluginfw.ERROR)
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
        else:
            pluginfw.AddLog(f"Skipping device {devicename}, missing device properties for import into Netbox", pluginfw.ERROR)
            pluginfw.AddLog(f"Properties:\n\
                Managment IP: {mgmtIP}\n\
                Managment Intf: {mgmtIntf}\n\
                Vendor: {vendor}\n\
                Model: {model}\n\
                Device Type: {subTypeName}\n\
                Site: {siteName}\n\
                Role: {mainTypeName}\
                ", pluginfw.ERROR)
    
    return True
