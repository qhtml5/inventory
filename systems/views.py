import csv

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator, InvalidPage, EmptyPage

from django.db.models import Q
from django.http import HttpResponse, HttpResponseRedirect
from django.shortcuts import  redirect, get_object_or_404
from django.template import RequestContext
from django.template.loader import render_to_string
try:
    import json
except:
    from django.utils import simplejson as json
import _mysql_exceptions

import models
from mozilla_inventory.middleware.restrict_to_remote import allow_anyone,sysadmin_only, LdapGroupRequired

import re
from django.test.client import Client
from jinja2.filters import contextfilter
from django.utils import translation
from libs.jinja import render_to_response as render_to_response
from jingo import render
from django.views.decorators.csrf import csrf_exempt
from Rack import Rack

from core.interface.static_intr.models import StaticInterface

# Source: http://nedbatchelder.com/blog/200712/human_sorting.html
# Author: Ned Batchelder
def tryint(s):
    try:
        return int(s)
    except:
        return s

def alphanum_key(s):
    """ Turn a string into a list of string and number chunks.
        "z23a" -> ["z", 23, "a"]
    """
    return [ tryint(c) for c in re.split('([0-9]+)', s) ]

def sort_nicely(l):
    """ Sort the given list in the way that humans expect.
    """
    l.sort(key=alphanum_key)
def parse_title_num(title):
   val = 0
   try:
      val = int(title.rsplit('#')[-1])
   except ValueError:
      pass
   return val

def check_dupe_nic(request,system_id,adapter_number):
    try:
        system = models.System.objects.get(id=system_id)
        found = system.check_for_adapter(adapter_number)
    except:
        pass
    return HttpResponse(found)
def check_dupe_nic_name(requessdft,system_id,adapter_name):
    try:
        system = models.System.objects.get(id=system_id)
        found = system.check_for_adapter_name(adapter_name)
    except:
        pass
    return HttpResponse(found)
@allow_anyone
def system_rack_elevation(request, rack_id):
    r = Rack(rack_id)
    data  = {
            'rack_ru': r.ru,
            'ethernet_patch_panels_24': r.ethernet_patch_panel_24,
            'ethernet_patch_panels_48': r.ethernet_patch_panel_48,
            'systems': r.systems,
    }
    data = json.dumps(data)
    return render_to_response('systems/rack_elevation.html', {
        'data':data,
        },
        RequestContext(request))

@allow_anyone
def system_auto_complete_ajax(request):
    query = request.GET['query']
    system_list = models.System.objects.filter(hostname__icontains=query)
    hostname_list = [system.hostname for system in system_list]
    id_list = [system.id for system in system_list]
    ret_dict = {}
    ret_dict['query'] = query
    ret_dict['suggestions'] = hostname_list
    ret_dict['data'] = id_list
    return HttpResponse(json.dumps(ret_dict))

@allow_anyone
def list_all_systems_ajax(request):
#iSortCol_0 = which column is sorted
#sSortDir_0 = which direction   
    
    cols = ['hostname','serial','asset_tag','server_model','system_rack', 'oob_ip', 'system_status']
    sort_col = cols[0]
    if 'iSortCol_0' in request.GET:
        sort_col = cols[int(request.GET['iSortCol_0'])]

    sort_dir = 'asc'
    if 'sSortDir_0' in request.GET:
        sort_dir = request.GET['sSortDir_0']


    if 'sEcho' in request.GET:
        sEcho = request.GET['sEcho']

    if 'sSearch' in request.GET and request.GET['sSearch'] > '':
        search_term = request.GET['sSearch']
    else:
        search_term = None

    if 'iDisplayLength' in request.GET and request.GET['iDisplayLength'] > '':
        iDisplayLength = request.GET['iDisplayLength']
    else:
        iDisplayLength = 100

    if 'iDisplayStart' in request.GET and request.GET['iDisplayStart'] > '':
        iDisplayStart = request.GET['iDisplayStart']
    else:
        iDisplayStart = 0

    if search_term is None:
        end_display = int(iDisplayStart) + int(iDisplayLength)
        system_count = models.System.objects.all().count()
        systems = models.System.objects.all()[iDisplayStart:end_display]
        the_data = build_json(request, systems, sEcho, system_count, iDisplayLength, sort_col, sort_dir)

    if search_term is not None and len(search_term) > 0:
        if search_term.startswith('/') and len(search_term) > 1:
            try:
                search_term = search_term[1:]
                search_q = Q(hostname__regex=search_term)
            except:
                search_q = Q(hostname__icontains=search_term)
        else:
            search_q = Q(hostname__icontains=search_term)
        search_q |= Q(serial__contains=search_term)
        search_q |= Q(notes__contains=search_term)
        search_q |= Q(asset_tag=search_term)
        search_q |= Q(oob_ip__contains=search_term)
        try:
            total_count = models.System.with_related.filter(search_q).count()
        except:
            total_count = 0
        search_q |= Q(keyvalue__value__contains=search_term)
        end_display = int(iDisplayStart) + int(iDisplayLength)
        try:
            systems = models.System.with_related.filter(search_q).order_by('hostname').distinct('hostname')[iDisplayStart:end_display]
            the_data = build_json(request, systems, sEcho, total_count, iDisplayLength, sort_col, sort_dir)
        except:
            the_data = '{"sEcho": %s, "iTotalRecords":0, "iTotalDisplayRecords":0, "aaData":[]}' % (sEcho) 
    return HttpResponse(the_data)

def build_json(request, systems, sEcho, total_records, display_count, sort_col, sort_dir):
    system_list = []
    for system in systems:
        if system.serial is not None:
            serial = system.serial.strip()
        else:
            serial = ''

        if system.server_model is not None:
            server_model = str(system.server_model)
        else:
            server_model = ''
        if system.system_rack is not None:
            system_rack = "%s - %s" % (str(system.system_rack), system.rack_order)
            system_rack_id = str(system.system_rack.id)
        else:
            system_rack = ''
            system_rack_id = ''

        if system.system_status is not None:
            system_status = str(system.system_status)
        else:
            system_status = ''

        if system.asset_tag is not None:
            asset_tag = system.asset_tag.strip()
        else:
            asset_tag = ''
        if system.oob_ip is not None:
            oob_ip = system.oob_ip.strip()
        else:
            oob_ip = ''

        ro = getattr(request, 'read_only', False)
        if ro:
            system_id = 0
        else:
            system_id = system.id

        system_list.append({'hostname': system.hostname.strip(), 'oob_ip': oob_ip, 'serial': serial, 'asset_tag': asset_tag, 'server_model': server_model,
        'system_rack':system_rack, 'system_status':system_status, 'id':system_id, 'system_rack_id': system_rack_id})

    the_data = '{"sEcho": %s, "iTotalRecords":0, "iTotalDisplayRecords":0, "aaData":[]}' % (sEcho)

    #try:
    if len(system_list) > 0:
        system_list.sort(key=lambda x: alphanum_key(x[sort_col]))
        if sort_dir == 'desc':
            #system_list = system_list.reverse()
            system_list.reverse()


        #the_data = '{"sEcho": %s, "iTotalRecords":%i, "iTotalDisplayRecords":%s, "aaData":[' % (sEcho,  total_records, display_count)
        the_data = '{"sEcho": %s, "iTotalRecords":%i, "iTotalDisplayRecords":%i, "aaData":[' % (sEcho,  total_records, total_records)
        #sort_nicely(system_list)
        counter = 0
        for system in system_list:
            if counter < display_count:
                the_data += '["%i,%s","%s","%s","%s","%s,%s", "%s", "%s", "%i"],' % (system['id'],system['hostname'], system['serial'],system['asset_tag'],system['server_model'],system['system_rack_id'], system['system_rack'], system['oob_ip'], system['system_status'], system['id'])
                counter += 1
            else:
                counter = display_count
        the_data = the_data[:-1]
        the_data += ']}'
    #except:
        pass
    
    return the_data 


#@ldap_group_required('build')
#@LdapGroupRequired('build_team', exclusive=False)
@allow_anyone
def home(request):
    """Index page"""
    return render_to_response('systems/index.html', {
            'read_only': getattr(request, 'read_only', False),
            #'is_build': getattr(request.user.groups.all(), 'build', False),
           })

@allow_anyone
def system_quicksearch_ajax(request):
    """Returns systems sort table"""
    search_term = request.POST['quicksearch']
    search_q = Q(hostname__icontains=search_term)
    search_q |= Q(serial__contains=search_term)
    search_q |= Q(notes__contains=search_term)
    search_q |= Q(asset_tag=search_term)
    systems = models.System.with_related.filter(search_q).order_by('hostname')
    if 'is_test' not in request.POST:
        return render_to_response('systems/quicksearch.html', {
                'systems': systems,
                'read_only': getattr(request, 'read_only', False),
            },
            RequestContext(request))
    else:
        from django.core import serializers
        systems_data = serializers.serialize("json", systems)
        return HttpResponse(systems_data)

def get_key_value_store(request, id):
    system = models.System.objects.get(id=id)
    key_value_store = models.KeyValue.objects.filter(system=system)
    return render_to_response('systems/key_value_store.html', {
            'key_value_store': key_value_store,
           },
           RequestContext(request))
def delete_key_value(request, id, system_id):
    kv = models.KeyValue.objects.get(id=id)
    matches = re.search('^nic\.(\d+)', str(kv.key) )
    if matches:
        try:
            existing_dhcp_scope = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.dhcp_scope.0' % matches.group(1))[0].value
            models.ScheduledTask(task=existing_dhcp_scope, type='dhcp').save()
        except:
            pass
    kv.delete()
    system = models.System.objects.get(id=system_id)
    key_value_store = models.KeyValue.objects.filter(system=system)
    return render_to_response('systems/key_value_store.html', {
            'key_value_store': key_value_store,
           },
           RequestContext(request))
@csrf_exempt
def save_key_value(request, id):
    system_id = None
    kv = models.KeyValue.objects.get(id=id)
    if kv is not None:
        ##Here we eant to check if the existing key is a network adapter. If so we want to find out if it has a dhcp scope. If so then we want to add it to ScheduledTasks so that the dhcp file gets regenerated
        matches = re.search('^nic\.(\d+)', str(kv.key).strip() )
        if matches and matches.group(1):
            try:
                existing_dhcp_scope = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.dhcp_scope.0' % matches.group(1))[0].value
                if existing_dhcp_scope is not None:
                    models.ScheduledTask(task=existing_dhcp_scope, type='dhcp').save()
            except Exception, e: 
                pass
            try:
                existing_reverse_dns_zone = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.reverse_dns_zone.0' % matches.group(1))[0].value
                if existing_reverse_dns_zone is not None:
                    models.ScheduledTask(task=existing_reverse_dns_zone, type='reverse_dns_zone').save()
            except Exception, e: 
                pass
        try:
            kv.key = request.POST.get('key').strip()
            kv.value = request.POST.get('value').strip()
            system_id = str(kv.system_id)
            kv.save() # This is going to be throwing usefull exceptions. We should figure out a way to forward them to users.
        except:
            kv.key = None
            kv.value = None
        ##Here we eant to check if the new key is a network adapter. If so we want to find out if it has a dhcp scope. If so then we want to add it to ScheduledTasks so that the dhcp file gets regenerated
        if kv.key is not None:
            matches = re.search('nic\.(\d+)', kv.key)
            if matches and matches.group(1):
                new_dhcp_scope = None
                new_reverse_dns_zone = None
                try:
                    new_dhcp_scope = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.dhcp_scope.0' % matches.group(1))[0].value
                except Exception, e:
                    pass

                try:
                    new_reverse_dns_zone = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.reverse_dns_zone.0' % matches.group(1))[0].value
                except Exception, e:
                    pass
                if new_dhcp_scope is not None:
                    try:
                        models.ScheduledTask(task=new_dhcp_scope, type='dhcp').save()
                    except Exception, e:
                        print e
                        ##This is due to the key already existing in the db
                        pass
                if new_reverse_dns_zone is not None:
                    try:
                        models.ScheduledTask(task=new_reverse_dns_zone, type='reverse_dns_zone').save()
                    except Exception ,e:
                        print e
                        ##This is due to the key already existing in the db
                        pass


    return HttpResponseRedirect('/en-US/systems/get_key_value_store/' + system_id + '/')

@csrf_exempt
def create_key_value(request, id):
    system = models.System.objects.get(id=id)
    key = 'None'
    value = 'None'
    print request.POST
    if 'key' in request.POST:
        key = request.POST['key'].strip()
    if 'value' in request.POST:
        value = request.POST['value'].strip()
    kv = models.KeyValue(system=system,key=key,value=value)
    print "Key is %s: Value is %s." % (key, value)
    kv.save();
    matches = re.search('^nic\.(\d+)', str(kv.key) )
    if matches:
        try:
            existing_dhcp_scope = models.KeyValue.objects.filter(system=kv.system).filter(key='nic.%s.dhcp_scope.0' % matches.group(1))[0].value
            models.ScheduledTask(task=existing_dhcp_scope, type='dhcp').save()
        except:
            pass
    key_value_store = models.KeyValue.objects.filter(system=system)
    return render_to_response('systems/key_value_store.html', {
            'key_value_store': key_value_store,
           },
           RequestContext(request))
def get_network_adapters(request, id):
    adapters = models.NetworkAdapter.objects.filter(system_id=id)
    return render_to_response('systems/network_adapters.html', {
            'adapters': adapters,
            'switches': models.System.objects.filter(is_switch=1),
            'dhcp_scopes': models.DHCP.objects.all()
            #'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))
def delete_network_adapter(request, id, system_id):
    adapter = models.NetworkAdapter.objects.get(id=id)
    adapter.delete()
    adapters = models.NetworkAdapter.objects.filter(system_id=system_id)
    return render_to_response('systems/network_adapters.html', {
            'adapters': adapters,
            'dhcp_scopes': models.DHCP.objects.all(),
            'switches': models.System.objects.filter(is_switch=1)
            #'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))

def create_network_adapter(request, id):

    nic = models.NetworkAdapter(system_id=id)
    nic.save()
    adapters = models.NetworkAdapter.objects.filter(system_id=id)
    return render_to_response('systems/network_adapters.html', {
            'adapters': adapters,
            'dhcp_scopes': models.DHCP.objects.all(),
            'switches': models.System.objects.filter(is_switch=1)
            #'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))

def save_network_adapter(request, id):
    import re
    nic = models.NetworkAdapter.objects.get(id=id)
    if nic is not None:
        mac = request.POST['mac_address']
        mac = mac.replace(':','').replace(' ','').replace('.','')
        tmp = mac[0:2] + ':' + mac[2:4] + ':' + mac[4:6] + ':' + mac[6:8] + ':' + mac[8:10] + ':' + mac[10:12]
        mac = tmp
        nic.dhcp_scope_id = request.POST['dhcp_scope_id']
        nic.mac_address = mac
        nic.ip_address = request.POST['ip_address']
        nic.filename = request.POST['filename']
        nic.option_host_name = request.POST['option_host_name']
        nic.option_domain_name = request.POST['option_domain_name']
        nic.adapter_name = request.POST['adapter_name']
        if request.POST['switch_id']:
            nic.switch_id = request.POST['switch_id']
        else:
            nic.switch_id = None
        nic.switch_port = request.POST['switch_port']
        nic.save()
    return HttpResponseRedirect('/systems/get_network_adapters/' + id)





@allow_anyone
def system_show(request, id):
    system = get_object_or_404(models.System, pk=id)
    is_release = False
    try:
        client = Client()
        adapters = json.loads(client.get('/api/v2/keyvalue/3/', {'key_type':'adapters_by_system','system':system.hostname}, follow=True).content)
    except:
        adapters = []
    if system.allocation is 'release':
        is_release = True
    if (system.serial and
            system.server_model and
            system.server_model.part_number and
            system.server_model.vendor == "HP"):

        system.warranty_link = "http://www11.itrc.hp.com/service/ewarranty/warrantyResults.do?productNumber=%s&serialNumber1=%s&country=US" % (system.server_model.part_number, system.serial)

    intrs = StaticInterface.objects.filter(system = system)

    return render_to_response('systems/system_show.html', {
            'system': system,
            'interfaces': intrs,
            'adapters': adapters,
            'is_release': is_release,
            'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))

@allow_anyone
def system_show_by_asset_tag(request, id):
    system = get_object_or_404(models.System, asset_tag=id)
    is_release = True
    if system.allocation is 'release':
        is_release = True
    if (system.serial and
            system.server_model and
            system.server_model.part_number and
            system.server_model.vendor == "HP"):

        system.warranty_link = "http://www11.itrc.hp.com/service/ewarranty/warrantyResults.do?productNumber=%s&serialNumber1=%s&country=US" % (system.server_model.part_number, system.serial)

    return render_to_response('systems/system_show.html', {
            'system': system,
            'is_release': True,
            'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))

def system_view(request, template, data, instance=None):
    from forms import SystemForm
    if request.method == 'POST':
        form = SystemForm(request.POST, instance=instance)
        if form.is_valid():
            s = form.save(commit=False)
            s.save(request=request)
            return redirect(system_show, s.pk)
    else:
        form = SystemForm(instance=instance)

    data['form'] = form

    return render_to_response(template, 
                data,
                request
            )
@csrf_exempt
def system_new(request):
    return system_view(request, 'systems/system_new.html', {})

@csrf_exempt
def system_edit(request, id):
    system = get_object_or_404(models.System, pk=id)
    client = Client()
    dhcp_scopes = None
    try:
        dhcp_scopes = json.loads(client.get('/api/v2/dhcp/phx-vlan73/get_scopes_with_names/', follow=True).content)
    except Exception, e:
        print e
        pass

    return system_view(request, 'systems/system_edit.html', {
            'system': system,
            'dhcp_scopes':dhcp_scopes,
            'revision_history':models.SystemChangeLog.objects.filter(system=system).order_by('-id')
            }, system)


def system_delete(request, id):
    system = get_object_or_404(models.System, pk=id)
    system.delete()
    return redirect(home)


def system_csv(request):
    systems = models.System.objects.all().order_by('hostname')

    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=systems.csv'

    writer = csv.writer(response)
    writer.writerow(['Host Name', 'Serial', 'Asset Tag', 'Model', 'Allocation', 'Rack', 'Switch Ports', 'OOB IP'])
    for s in systems:
        try:
            writer.writerow([s.hostname, s.serial, s.asset_tag, s.server_model, s.allocation, s.system_rack, s.switch_ports, s.oob_ip])
        except:
            writer.writerow([s.hostname, s.serial, s.asset_tag, s.server_model, '', s.system_rack, s.switch_ports, s.oob_ip])
        

    return response

def system_releng_csv(request):
    systems = models.System.objects.filter(allocation=2).order_by('hostname')

    response = HttpResponse(mimetype='text/csv')
    response['Content-Disposition'] = 'attachment; filename=systems.csv'

    writer = csv.writer(response)
    writer.writerow(['id','hostname', 'switch_ports', 'oob_ip', 'system_rack', 'asset_tag', 'operating_system', 'rack_order'])
    for s in systems:
        writer.writerow([s.id, s.hostname, s.switch_ports, s.oob_ip, s.system_rack, s.asset_tag, s.operating_system, s.rack_order])

    return response

def get_expanded_key_value_store(request, system_id):
    try:
        from django.test.client import Client
        client = Client()
        system = models.System.objects.get(id=system_id)
        resp = client.get('/api/keyvalue/?keystore=%s' % (system.hostname), follow=True)
        return_obj = resp.content.replace("\n","<br />")
    except:
        return_obj = 'This failed'
    return HttpResponse(return_obj)


    
def new_rack_system_ajax(request, rack_id):
    from forms import RackSystemForm
    rack = get_object_or_404(models.SystemRack, pk=rack_id)

    data = {}
    resp_data = {}
    template = 'systems/rack_form_partial.html'
    if request.method == 'POST':
        rack_form = RackSystemForm(request.POST)
        if rack_form.is_valid():
            new_system = rack_form.save(commit=False)
            new_system.system_rack = rack
            new_system.save()

            data['system'] = new_system
            resp_data['success'] = True
            template = 'systems/rack_row_partial.html'
        else:
            resp_data['success'] = False
    else:
        rack_form = RackSystemForm()

    data['form'] = rack_form
    data['rack'] = rack

    resp_data['payload'] = render_to_string(template, data, RequestContext(request))

    return HttpResponse(json.dumps(resp_data), mimetype="application/json")

@allow_anyone
def racks_by_location(request, location=0):
    ret_list = []
    if int(location) > 0:
        location = models.Location.objects.get(id=location)
        racks = models.SystemRack.objects.select_related('location').filter(location=location).order_by('name')
    else:
        racks = models.SystemRack.objects.select_related('location').order_by('location', 'name')

    for r in racks:
        ret_list.append({'name':'%s %s' % (r.location.name, r.name), 'id':r.id})
    return HttpResponse(json.dumps(ret_list))

@allow_anyone
def racks(request):
    from forms import RackFilterForm
    filter_form = RackFilterForm(request.GET)

    racks = models.SystemRack.objects.select_related('location')

    system_query = Q()
    if 'location' in request.GET:
        location_id = request.GET['location']
        has_query = True
        if len(location_id) > 0 and int(location_id) > 0:
            loc = models.Location.objects.get(id=location_id)
            filter_form.fields['rack'].choices = [('','ALL')] + [(m.id, m.location.name + ' ' +  m.name) for m in models.SystemRack.objects.filter(location=loc).order_by('name')]
    else:
        has_query = False
    if filter_form.is_valid():

        if filter_form.cleaned_data['rack']:
            racks = racks.filter(id=filter_form.cleaned_data['rack'])
            has_query = True
        if filter_form.cleaned_data['location'] and int(filter_form.cleaned_data['location']) > 0:
            racks = racks.filter(location=filter_form.cleaned_data['location'])
            has_query = True
        if filter_form.cleaned_data['allocation']:
            system_query &= Q(allocation=filter_form.cleaned_data['allocation'])
            has_query = True
        if filter_form.cleaned_data['status']:
            system_query &= Q(system_status=filter_form.cleaned_data['status'])
            has_query = True
    ##Here we create an object to hold decommissioned systems for the following filter
    if not has_query:
        racks = []
    else:
        decommissioned = models.SystemStatus.objects.get(status='decommissioned')
        racks = [(k, list(k.system_set.select_related(
            'server_model',
            'allocation',
            'system_status',
        ).filter(system_query).exclude(system_status=decommissioned).order_by('rack_order'))) for k in racks]

    return render_to_response('systems/racks.html', {
            'racks': racks,
            'filter_form': filter_form,
            'read_only': getattr(request, 'read_only', False),
           },
           RequestContext(request))

def getoncall(request, type):
    from django.contrib.auth.models import User
    if type == 'desktop':
        try:
            return_irc_nick = User.objects.select_related().filter(userprofile__current_desktop_oncall=1)[0].get_profile().irc_nick
        except:
            return_irc_nick = ''
    if type == 'sysadmin':
        try:
            return_irc_nick = User.objects.select_related().filter(userprofile__current_sysadmin_oncall=1)[0].get_profile().irc_nick
        except:
            return_irc_nick = ''
    return HttpResponse(return_irc_nick)
def oncall(request):
    from forms import OncallForm
    from django.contrib.auth.models import User
    #current_desktop_oncall = models.UserProfile.objects.get_current_desktop_oncall
    try:
        current_desktop_oncall = User.objects.select_related().filter(userprofile__current_desktop_oncall=1)[0].username
    except IndexError:
        current_desktop_oncall = ''
    try:
        current_sysadmin_oncall = User.objects.select_related().filter(userprofile__current_sysadmin_oncall=1)[0].username
    except IndexError:
        current_sysadmin_oncall = ''
    initial = {
        'desktop_support':current_desktop_oncall,
        'sysadmin_support':current_sysadmin_oncall,
            }
    if request.method == 'POST':
        form = OncallForm(request.POST, initial=initial)
        if form.is_valid():
            """
               Couldn't get the ORM to update properly so running a manual transaction. For some reason, the model refuses to refresh
            """
            from django.db import connection, transaction
            cursor = connection.cursor()
            cursor.execute("UPDATE `user_profiles` set `current_desktop_oncall` = 0, `current_sysadmin_oncall` = 0")
            transaction.commit_unless_managed()

            ## There should only be one set oncall, but just in case it's cheap to loop through
            ## @TODO Figure out why the orm won't update correctly after this transaction
            """current_sysadmin_oncalls = User.objects.select_related().filter(userprofile__current_sysadmin_oncall=1)
            for c in current_sysadmin_oncalls:
                c.get_profile().current_sysadmin_oncall = 0
                c.get_profile().current_desktop_oncall = 0
                c.get_profile().save()
                c.save()
            User.objects.update()
            ## There should only be one set oncall, but just in case it's cheap to loop through
            current_desktop_oncalls = User.objects.select_related().filter(userprofile__current_desktop_oncall=1)
            for c in current_desktop_oncalls:
                c.get_profile().current_desktop_oncall = 0
                c.get_profile().save()
                c.save()
            User.objects.update()"""

            current_desktop_oncall = form.cleaned_data['desktop_support']
            current_sysadmin_oncall = form.cleaned_data['sysadmin_support']
            if current_desktop_oncall != current_sysadmin_oncall:
                set_oncall('desktop', current_desktop_oncall)
                set_oncall('sysadmin', current_sysadmin_oncall)
            elif current_desktop_oncall == current_sysadmin_oncall:
                set_oncall('both', current_sysadmin_oncall)
    else:
        form = OncallForm(initial = initial)
    return render(request, 'systems/generic_form.html', {'current_desktop_oncall':current_desktop_oncall,'current_sysadmin_oncall':current_sysadmin_oncall, 'form':form})
def set_oncall(type, username):
    from django.contrib.auth.models import User
    try:
        new_oncall = User.objects.get(username=username)
        if type=='desktop':
            new_oncall.get_profile().current_desktop_oncall = 1
        elif type=='sysadmin':
            new_oncall.get_profile().current_sysadmin_oncall = 1
        elif type=='both':
            new_oncall.get_profile().current_sysadmin_oncall = 1
            new_oncall.get_profile().current_desktop_oncall = 1
        new_oncall.get_profile().save()
        new_oncall.save()
    except Exception, e:
        print e
def rack_delete(request, object_id):
    from models import SystemRack
    rack = get_object_or_404(SystemRack, pk=object_id)
    if request.method == "POST":
        rack.delete()
        return HttpResponseRedirect('/systems/racks/')
    else:
        return render_to_response('systems/rack_confirm_delete.html', {
                'rack': rack,
            },
            RequestContext(request))

def rack_edit(request, object_id):
    rack = get_object_or_404(models.SystemRack, pk=object_id)
    from forms import SystemRackForm
    initial = {}
    if request.method == 'POST':
        form = SystemRackForm(request.POST, instance=rack)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/racks/')
    else:
        form = SystemRackForm(instance=rack)

    return render_to_response('systems/generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def rack_new(request):
    from forms import SystemRackForm
    initial = {}
    if request.method == 'POST':
        form = SystemRackForm(request.POST, initial=initial)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/racks/')
    else:
        form = SystemRackForm(initial=initial)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def location_show(request, object_id):
    object = get_object_or_404(models.Location, pk=object_id)

    return render_to_response('systems/location_detail.html', {
            'object': object,
           },
           RequestContext(request))
def location_edit(request, object_id):
    location = get_object_or_404(models.Location, pk=object_id)
    from forms import LocationForm
    initial = {}
    if request.method == 'POST':
        form = LocationForm(request.POST, instance=location)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/locations/')
    else:
        form = LocationForm(instance=location)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def location_new(request):
    from forms import LocationForm
    initial = {}
    if request.method == 'POST':
        form = LocationForm(request.POST, initial=initial)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/locations/')
    else:
        form = LocationForm(initial=initial)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def server_model_edit(request, object_id):
    server_model = get_object_or_404(models.ServerModel, pk=object_id)
    from forms import ServerModelForm
    initial = {}
    if request.method == 'POST':
        form = ServerModelForm(request.POST, instance=server_model)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/server_models/')
    else:
        form = ServerModelForm(instance=server_model)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))

@csrf_exempt
def operating_system_create_ajax(request):
    if request.method == "POST":
        if 'name' in request.POST and 'version' in request.POST:
            name = request.POST['name']
            version = request.POST['version']
        models.OperatingSystem(name=name,version=version).save()
        return operating_system_list_ajax(request)
    else:
        return HttpResponse("OK")

@csrf_exempt
def server_model_create_ajax(request):
    if request.method == "POST":
        if 'model' in request.POST and 'vendor' in request.POST:
            model = request.POST['model']
            vendor = request.POST['vendor']
        models.ServerModel(vendor=vendor,model=model).save()
        return server_model_list_ajax(request)
    else:
        return HttpResponse("OK")

def operating_system_list_ajax(request):
    ret = []
    for m in models.OperatingSystem.objects.all():
        ret.append({'id':m.id, 'name': "%s - %s" % (m.name, m.version)})

    return HttpResponse(json.dumps(ret))

def server_model_list_ajax(request):
    ret = []
    for m in models.ServerModel.objects.all():
        ret.append({'id':m.id, 'name': "%s - %s" % (m.vendor, m.model)})

    return HttpResponse(json.dumps(ret))

def server_model_show(request, object_id):
    object = get_object_or_404(models.ServerModel, pk=object_id)

    return render_to_response('systems/servermodel_detail.html', {
            'object': object,
           },
           RequestContext(request))
def server_model_list(request):
    object_list = models.ServerModel.objects.all()
    print object_list
    return render_to_response('systems/servermodel_list.html', {
            'object_list': object_list,
           },
           RequestContext(request))
def allocation_show(request, object_id):
    object = get_object_or_404(models.Allocation, pk=object_id)

    return render_to_response('systems/allocation_detail.html', {
            'object': object,
           },
           RequestContext(request))
def allocation_edit(request, object_id):
    allocation = get_object_or_404(models.Allocation, pk=object_id)
    from forms import AllocationForm
    initial = {}
    if request.method == 'POST':
        form = AllocationForm(request.POST, instance=allocation)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/allocations/')
    else:
        form = AllocationForm(instance=allocation)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def allocation_list(request):
    object_list = models.Allocation.objects.all()
    return render_to_response('systems/allocation_list.html', {
            'object_list': object_list,
           },
           RequestContext(request))
def allocation_new(request):
    from forms import AllocationForm
    initial = {}
    if request.method == 'POST':
        form = AllocationForm(request.POST, initial=initial)
        if form.is_valid():
            form.save()
            return HttpResponseRedirect('/systems/allocations/')
    else:
        form = AllocationForm(initial=initial)

    return render_to_response('generic_form.html', {
            'form': form,
           },
           RequestContext(request))
def location_list(request):
    object_list = models.Location.objects.all()
    return render_to_response('systems/location_list.html', {
            'object_list': object_list,
           },
           RequestContext(request))
def csv_import(request):
    from forms import CSVImportForm
    def generic_getter(field):
        return field

    def uppercase_getter(field):
        return field.upper()

    def allocation_getter(field):
        try:
            return models.Allocation.objects.get(name=field)
        except models.Allocation.DoesNotExist:
            return None

    def system_status_getter(field):
        try:
            return models.SystemStatus.objects.get(status=field)
        except models.SystemStatus.DoesNotExist:
            return

    def server_model_getter(field):
        try:
            return models.ServerModel.objects.get(id=field)
        except models.ServerModel.DoesNotExist:
            return

    def rack_getter(field):
        try:
            return models.SystemRack.objects.get(name=field)
        except models.SystemRack.DoesNotExist:
            return None

    ALLOWED_COLUMNS = {
        'hostname': generic_getter,
        'asset_tag': generic_getter,
        'serial': uppercase_getter,
        'notes': generic_getter,
        'oob_ip': generic_getter,
        'system_status': system_status_getter,
        'allocation': allocation_getter,
        'system_rack': rack_getter,
        'rack_order': generic_getter,
        'server_model': server_model_getter,
        'purchase_price': generic_getter,
    }

    new_systems = 0
    if request.method == 'POST':
        form = CSVImportForm(request.POST, request.FILES)
        if form.is_valid():
            csv_reader = csv.reader(form.cleaned_data['csv'])
            headers = csv_reader.next()
            for line in csv_reader:
                cur_data = dict(zip(headers, line))

                system_data = dict((a, getter(cur_data.get(a, None)))
                                        for a, getter in ALLOWED_COLUMNS.iteritems())

                s = models.System(**system_data)
                try:
                    s.full_clean()
                except ValidationError, e:
                    print e
                else:
                    s.save()
                    new_systems += 1
            form = None
    else:
        form = CSVImportForm()

    return render_to_response('systems/csv_import.html', {
        'form': form,
        'allowed_columns': ALLOWED_COLUMNS,
        'new_systems': new_systems,
        },
        RequestContext(request))

