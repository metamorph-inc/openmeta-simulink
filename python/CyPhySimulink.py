
import sys
import os
#sys.path.append(r"C:\Program Files\ISIS\Udm\bin")
#if os.environ.has_key("UDM_PATH"):
#    sys.path.append(os.path.join(os.environ["UDM_PATH"], "bin"))
import _winreg as winreg
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\META") as software_meta:
    meta_path, _ = winreg.QueryValueEx(software_meta, "META_PATH")
sys.path.append(os.path.join(meta_path, 'bin'))
import udm
import pprint

class SimulinkModel(object):
    def __init__(self):
        self.objects = []

    @classmethod
    def from_test_bench(cls, test_bench):
        result = cls()
        result.add_objects_from_model(test_bench)
        return result

    def add_objects_from_model(self, model):
        # Attempt to instantiate this object as a SimulinkObject
        obj = SimulinkObject.from_domain_model(model)

        if obj is not None:
            self.objects.append(obj)

        # Recursively do the same for all children
        for child in model.children():
            self.add_objects_from_model(child)

    def __repr__(self):
        return pprint.pformat(self.objects)


class SimulinkObject(object):
    def __init__(self, name, block_path):
        self.name = name
        self.block_path = block_path
        self.outgoing_ports = []
        self.params = {}

    @classmethod
    def from_domain_model(cls, domainModelObject):
        '''Creates a SimulinkObject from the specified GenericDomainModel CyPhy object'''
        if object_is_simulink_domain_model(domainModelObject):
            name = get_domain_model_component_name(domainModelObject)
            result = cls(name, domainModelObject.Type)

            # Fetch parameters and connected objects
            for child in domainModelObject.children():
                if(child.type.name == "GenericDomainModelParameter"):
                    paramName = child.name
                    paramValue = get_adjacent_param_value(child)
                    result.params[paramName] = paramValue
                elif(child.type.name == "GenericDomainModelPort"):
                    if child.Type == "out":
                        newPort = SimulinkPort.from_out_port(child)
                        result.outgoing_ports.append(newPort)
                else:
                    pass

            return result
        else:
            return None

    def __repr__(self):
        return pprint.pformat(vars(self))

class SimulinkPort(object):
    def __init__(self, name):
        self.name = name
        self.connected_input_port_names = []
        pass

    @classmethod
    def from_out_port(cls, port):
        result = cls(port.name)
        result.add_connected_input_ports(port)
        return result

    def add_connected_input_ports(self, port, visited = set()):
        '''Adds connected input ports, if they're children of
           a GenericDomainModel'''
        visited.add(port)

        if port.Type == "in" and object_is_simulink_domain_model(port.parent):
            self.connected_input_port_names.append("{0}/{1}".format(get_domain_model_component_name(port.parent), port.name))

        for adjacent in port.adjacent():
            if adjacent not in visited:
                self.add_connected_input_ports(adjacent, visited)

    def __repr__(self):
        return pprint.pformat(vars(self))

def object_is_simulink_domain_model(o):
    return o.type.name == "GenericDomainModel" and (o.Domain == "simulink" or o.Domain == "Simulink")

def get_domain_model_component_name(model_object):
    # Object name actually comes from the containing Component (assuming that we have a containing component)
    return model_object.parent.name # TODO: verify that this actually is a component

def log(s):
    print s
try:
    import CyPhyPython # will fail if not running under CyPhyPython
    import cgi
    def log(s):
        CyPhyPython.log(cgi.escape(s))
except ImportError:
    pass

def log_formatted(s):
    print s
try:
    import CyPhyPython # will fail if not running under CyPhyPython
    import cgi
    def log(s):
        CyPhyPython.log(s)
except ImportError:
    pass

def start_pdb():
    ''' Starts pdb, the Python debugger, in a console window
    '''
    import ctypes
    ctypes.windll.kernel32.AllocConsole()
    import sys
    sys.stdout = open('CONOUT$', 'wt')
    sys.stdin = open('CONIN$', 'rt')
    import pdb; pdb.set_trace()

def log_object(o, indent=0):
    if o.type.name == "GenericDomainModel":
        log("{2}{0} - {1} - {3} - {4} -> {5}".format(o.name, o.type.name, '  '*indent, o.Domain, o.Type, get_adjacent_object_names(o)))
    elif o.type.name == "GenericDomainModelParameter":
        log("{2}{0} - {1} - {3}".format(o.name, o.type.name, '  '*indent, get_adjacent_param_value(o)))
    elif o.type.name == "GenericDomainModelPort":
        log("{2}{0} - {1} -> {3}".format(o.name, o.type.name, '  '*indent, get_adjacent_object_names(o)))
    else:
        log("{2}{0} - {1}".format(o.name, o.type.name, '  '*indent))

    for child in o.children():
        log_object(child, indent + 1)

def get_adjacent_object_names(o):
    adjacent = o.adjacent()
    return [get_full_path(a) for a in adjacent]

def get_adjacent_param_value(domainParam):
    adjacent = domainParam.adjacent()

    if(len(adjacent) != 1):
        return "Too many or too few connected nodes! ({0})".format(len(adjacent))
    else:
        return adjacent[0].Value

def get_full_path(o):
    path = []
    intermediate = o
    while intermediate != udm.null:
        path.insert(0, (intermediate.name, intermediate.type.name))
        intermediate = intermediate.parent

    return '/'.join(["{0} ({1})".format(name, typeName) for (name, typeName) in path])

# This is the entry point    
def invoke(focusObject, rootObject, componentParameters, **kwargs):
    #log(focusObject.name)
    #print repr(focusObject.name)
    #start_pdb()
    #log_object(focusObject)
    newModel = SimulinkModel.from_test_bench(focusObject)

    log(repr(newModel))

    componentParameters["runCommand"] = "cmd /c dir"

# Allow calling this script with a .mga file as an argument    
if __name__=='__main__':
    import _winreg as winreg
    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\META") as software_meta:
        meta_path, _ = winreg.QueryValueEx(software_meta, "META_PATH")

    # need to open meta DN since it isn't compiled in
    uml_diagram = udm.uml_diagram()
    meta_dn = udm.SmartDataNetwork(uml_diagram)
    import os.path
    CyPhyML_udm = os.path.join(meta_path, r"generated\CyPhyML\models\CyPhyML_udm.xml")
    if not os.path.isfile(CyPhyML_udm):
        CyPhyML_udm = os.path.join(meta_path, r"meta\CyPhyML_udm.xml")
    meta_dn.open(CyPhyML_udm, "")

    dn = udm.SmartDataNetwork(meta_dn.root)
    dn.open(sys.argv[1], "")
    # TODO: what should focusObject be
    # invoke(None, dn.root);
    dn.close_no_update()
    meta_dn.close_no_update()
