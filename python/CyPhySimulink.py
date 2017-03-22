from __future__ import unicode_literals

import sys
import os
#sys.path.append(r"C:\Program Files\ISIS\Udm\bin")
#if os.environ.has_key("UDM_PATH"):
#    sys.path.append(os.path.join(os.environ["UDM_PATH"], "bin"))
import _winreg as winreg
with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"Software\META") as software_meta:
    meta_path, _ = winreg.QueryValueEx(software_meta, "META_PATH")
sys.path.append(os.path.join(meta_path, 'bin'))

import datetime
import os.path
import pprint
import shutil
from cStringIO import StringIO

import udm
import six

class SimulinkModel(object):
    def __init__(self):
        self.blocks = []
        self.simulation_params = {}

    @classmethod
    def from_test_bench(cls, test_bench):
        result = cls()
        result.add_blocks_from_model(test_bench)
        result.get_simulation_params_from_test_bench(test_bench)
        return result

    def add_blocks_from_model(self, model):
        # Attempt to instantiate this object as a SimulinkBlock
        obj = SimulinkBlock.from_domain_model(model)

        if obj is not None:
            self.blocks.append(obj)

        # Recursively do the same for all children
        for child in model.children():
            self.add_blocks_from_model(child)

    def get_simulation_params_from_test_bench(self, model):
        if model.type.name != "TestBench":
            raise RuntimeError("Selected model is not a TestBench")

        for child in model.children():
            if child.type.name == "Parameter" and len(child.adjacent()) == 0:
                # Unconnected parameters must be simulation parameters
                if child.Value != "":
                    self.simulation_params[child.name] = child.Value

    def generate_simulink_model_code(self, out):
        out.write("% Generated by CyPhySimulink.py on {0}\n\n".format(datetime.datetime.now()))

        out.write("disp('Generating Simulink model; don''t close this window');\n\n")

        out.write("sys = CreateOrOverwriteModel('NewModel');\n")
        out.write("load_system(sys)\n\n")
        out.write("try\n")

        # We generate code in two phases here, because our blocks need to exist before we can connect them
        for o in self.blocks:
            o.generate_simulink_block_code(out)
        for o in self.blocks:
            o.generate_simulink_connection_code(out)

        out.write("catch me\n") # Catch errors during Simulink generation, so we don't get a unclosable "Do you want to save?" dialog
        out.write("save_system();\n")
        out.write("close_system();\n")
        out.write("rethrow(me);\n")
        out.write("end\n")

        out.write("\nsave_system();\n")
        out.write("close_system();\n")

    def generate_simulink_execution_code(self, out):
        out.write("% Generated by CyPhySimulink.py on {0}\n\n".format(datetime.datetime.now()))

        out.write("disp('Running Simulink simulation; don''t close this window');\n\n")

        out.write("load_system('NewModel');\n")
        out.write("try\n")
        out.write("sim(gcs");

        for name, value in six.iteritems(self.simulation_params):
            out.write(", '{param_name}', '{param_value}'".format(param_name=name, param_value=value))

        out.write(");\n")
        out.write("catch me\n") # Catch errors during Simulink generation, so we don't get a unclosable "Do you want to save?" dialog
        out.write("save_system();\n")
        out.write("close_system();\n")
        out.write("rethrow(me);\n")
        out.write("end\n")

        out.write("\nsave_system();\n")
        out.write("close_system();\n")

    def __repr__(self):
        return pprint.pformat(vars(self))


class SimulinkBlock(object):
    def __init__(self, name, block_path):
        self.name = name
        self.block_path = block_path
        self.outgoing_ports = []
        self.params = {}

    @classmethod
    def from_domain_model(cls, domainModelObject):
        '''Creates a SimulinkBlock from the specified GenericDomainModel CyPhy object'''
        if SimulinkBlock.object_is_simulink_domain_model(domainModelObject):
            name = SimulinkBlock.get_domain_model_component_name(domainModelObject)
            result = cls(name, domainModelObject.Type)

            # Fetch parameters and connected objects
            for child in domainModelObject.children():
                if(child.type.name == "GenericDomainModelParameter"):
                    paramName = child.name
                    paramValue = SimulinkBlock.get_adjacent_param_value(child)
                    # TODO: How do we distinguish unset values and values which were intentionally set to an empty string?
                    # For now, we consider the empty string (or no param value) to be unset, and don't set those params
                    if paramValue is not None and paramValue != "":
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

    def generate_simulink_block_code(self, out):
        # TODO: Handle Matlab-style string escaping (what needs to be escaped?)
        out.write("add_block('{block_path}', [gcs, '/{name}']);\n".format(block_path=self.block_path, name=self.name))

        for param_name, param_value in six.iteritems(self.params):
            out.write("set_param([gcs, '/{name}'], '{param_name}', '{param_value}');\n".format(name=self.name, param_name=param_name, param_value=param_value))

    def generate_simulink_connection_code(self, out):
        for port in self.outgoing_ports:
            for input_port_name in port.connected_input_port_names:
                out.write("add_line(gcs, '{name}/{port_name}', '{input_port_name}');\n".format(name=self.name, port_name=port.name, input_port_name=input_port_name))

    @staticmethod
    def object_is_simulink_domain_model(o):
        return o.type.name == "GenericDomainModel" and (o.Domain == "simulink" or o.Domain == "Simulink")

    @staticmethod
    def get_domain_model_component_name(model_object):
        # Object name actually comes from the containing Component (assuming that we have a containing component)
        return model_object.parent.name # TODO: verify that this actually is a component

    @staticmethod
    def get_adjacent_param_value(domainParam):
        adjacent = domainParam.adjacent()

        if(len(adjacent) != 1):
            return None
        else:
            return adjacent[0].Value

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

        if port.Type == "in" and SimulinkBlock.object_is_simulink_domain_model(port.parent):
            self.connected_input_port_names.append("{0}/{1}".format(SimulinkBlock.get_domain_model_component_name(port.parent), port.name))

        for adjacent in port.adjacent():
            if adjacent not in visited:
                self.add_connected_input_ports(adjacent, visited)

    def __repr__(self):
        return pprint.pformat(vars(self))

# This is the entry point    
def invoke(focusObject, rootObject, componentParameters, **kwargs):
    log(pprint.pformat(componentParameters))
    #log(focusObject.name)
    #print repr(focusObject.name)
    #start_pdb()
    log_object(focusObject)
    newModel = SimulinkModel.from_test_bench(focusObject)

    log(repr(newModel))

    # Copy support files
    output_dir = componentParameters["output_dir"]
    shutil.copy(os.path.join("matlab", "CreateOrOverwriteModel.m"), output_dir)

    with open(os.path.join(output_dir, "build_simulink.m"), "w") as out:
        newModel.generate_simulink_model_code(out)

    with open(os.path.join(output_dir, "run_simulink.m"), "w") as out:
        newModel.generate_simulink_execution_code(out)

    componentParameters["runCommand"] = "matlab.exe -nodisplay -nosplash -nodesktop -wait -r \"diary('matlab.out.txt'), try, run('build_simulink.m'), run('run_simulink.m'), catch me, fprintf('%s / %s\\n',me.identifier,me.message), exit(1), end, exit(0)\""

#CyPhyPython boilerplate stuff
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

# Debugging helper methods
def log_object(o, indent=0):
    if o.type.name == "GenericDomainModel":
        log("{2}{0} - {1} - {3} - {4} -> {5}".format(o.name, o.type.name, '  '*indent, o.Domain, o.Type, get_adjacent_object_names(o)))
    elif o.type.name == "GenericDomainModelParameter":
        log("{2}{0} - {1} - {3}".format(o.name, o.type.name, '  '*indent, SimulinkBlock.get_adjacent_param_value(o)))
    elif o.type.name == "GenericDomainModelPort":
        log("{2}{0} - {1} -> {3}".format(o.name, o.type.name, '  '*indent, get_adjacent_object_names(o)))
    else:
        log("{2}{0} - {1}".format(o.name, o.type.name, '  '*indent))

    for child in o.children():
        log_object(child, indent + 1)

def get_adjacent_object_names(o):
    adjacent = o.adjacent()
    return [get_full_path(a) for a in adjacent]

def get_full_path(o):
    path = []
    intermediate = o
    while intermediate != udm.null:
        path.insert(0, (intermediate.name, intermediate.type.name))
        intermediate = intermediate.parent

    return '/'.join(["{0} ({1})".format(name, typeName) for (name, typeName) in path])

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
