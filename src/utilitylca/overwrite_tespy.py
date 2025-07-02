from tespy.components import Source, Sink
from tespy.connections import Bus
from tespy.networks import Network

from tespy.tools import helpers as hlp

import bw2io as bi
import bw2data as bd
import bw2calc as bc

class Network(Network):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)

    def set_functional_unit(self, functional_unit):
        self.reference_comp= functional_unit

    def calc_background_impact(self, impact_categories):
        """Calculate the environmental impact of the network.

        Returns
        -------
        dict
            Dictionary with the environmental impact of the network.
        """
 
        self.method_config= {'impact_categories':impact_categories}
        self.functional_units={}
        self.background_flows={}
        for comp in self.comps['object']:
            if isinstance(comp, Sink) and hasattr(comp, 'bw_dataset'):
                self.functional_units[comp.label]={comp.bw_dataset.id:1}
            if isinstance(comp, Source) and hasattr(comp, 'bw_dataset'):
                self.functional_units[comp.label]={comp.bw_dataset.id:1}
        for label, bus in self.busses.items():
            if isinstance(bus, Bus) and hasattr(bus, 'bw_dataset'):
                self.functional_units[bus.label]={bus.bw_dataset.id:1}
                
        data_objs = bd.get_multilca_data_objs(self.functional_units, self.method_config)
        self.lca = bc.MultiLCA(demands=self.functional_units,
                    method_config=self.method_config, 
                    data_objs=data_objs
                    )
        self.lca.lci()
        self.lca.lcia()
    
    def get_lca_results(self):
        """Get the LCA results of the network.

        Parameters
        ----------
        reference_comp: sink, source, Bus
                Reference flow of the process for LCA.

        Returns
        -------
        dict
            Dictionary with the LCA results of the network.
        """
        if not hasattr(self, 'lca'):
            msg = 'No LCA results available. Please run calc_background_impact first.'
            raise hlp.TESPyNetworkError(msg)
        self.impact={}           
        self.background_flows={}
        for cat in self.method_config['impact_categories']:
            self.impact[cat] = 0
            for comp, _ in self.functional_units.items():
                impact=0
                reference_flow, tespy_component=self.get_reference_flow(comp)
                impact = self.lca.scores[(cat, comp)] * reference_flow
                self.impact[cat] += impact * tespy_component.bw_direction
            if self.get_reference_flow(self.reference_comp.label)!= False:
                func_flow, func_comp=self.get_reference_flow(self.reference_comp.label)
                self.impact[cat] = self.impact[cat]/func_flow*func_comp.bw_direction
            else:
                msg = ('No reference flow defined. Absolut impact calculated.'
                        'Call: set_functional_unit(functional_unit)' 
                        'to define a reference flow.'      
                )
                raise hlp.TESPyNetworkError(msg)
        return self.impact

    def get_reference_flow(self, comp):
        reference_flow = 0
        tespy_component= None
        if comp in self.comps['object'].index:
            tespy_component= self.comps.loc[comp]['object']
            if isinstance(tespy_component, Sink):
                reference_flow= tespy_component.inl[0].m.val
                
            elif isinstance(tespy_component, Source):
                reference_flow= tespy_component.outl[0].m.val
                
        elif comp in self.busses.keys():
            tespy_component= self.busses[comp]
            reference_flow= tespy_component.P.val
        else:
            return False
        return reference_flow, tespy_component
        

    def export_bw_dataset(self, database=None):
        pass


class Source(Source):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction
    
    def set_functional_unit(self,functional_unit: bool ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit

class Sink(Sink):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction

    def set_functional_unit(self,functional_unit: bool ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit


class Bus(Bus):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        r'''
        Link a brightway25 dataset to the Bus. 

        Parameters
        ----------
        bw_dataset: bw_dataset. Dataset representing the background activity of the flow.
        bw_direction: bool. Can be used for example for substitution of flows to invert the impact. 

        '''
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction
        
    def set_functional_unit(self,functional_unit: bool ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit