from tespy.components import (Source as tSource, Sink as tSink,
                              PowerSource as tPowerSource , PowerSink as tPowerSink)
from tespy.networks import Network as tNetwork

from tespy.tools import helpers as hlp

import bw2io as bi
import bw2data as bd
import bw2calc as bc

class functional_units():
    #TODO
    def __init__(self, components: list, allocationfactors: list) -> None:
        self.components= components
        self.allocationfactors= allocationfactors
        #for comp in components:      


class Network(tNetwork):
    def __init__(self,**kwargs):
        super().__init__(**kwargs)

    def set_functional_unit(self, functional_units: dict):
        """
        Set the functional units of the process.

        Parameters
        ----------
        functional_units: dict of the structure:
                {technosphere flow name: {
                    component: tespy component of type sink, source, PowerSource, PowerSink 
                    allocationfactor: factor to allocate the impact
                    
                    }
                }
                
                Reference flow of the process for LCA.

        """
        self.functional_units= functional_units

    def calc_background_impact(self, impact_categories):
        """Calculate the environmental impact of the network.

        Returns
        -------
        dict
            Dictionary with the environmental impact of the network.
        """
 
        self.method_config= {'impact_categories':impact_categories}
        self.technosphere_flows={}
        self.background_flows={}
        for comp in self.comps['object']:
            if hasattr(comp, 'bw_dataset'):
                if isinstance(comp, (Sink, Source, PowerSource, PowerSink)):
                    self.technosphere_flows[comp.label]={comp.bw_dataset.id:1}
              
        data_objs = bd.get_multilca_data_objs(self.technosphere_flows, self.method_config)
        self.lca = bc.MultiLCA(demands=self.technosphere_flows,
                    method_config=self.method_config, 
                    data_objs=data_objs
                    )
        self.lca.lci()
        self.lca.lcia()
    
    def get_lca_results(self):
        """Get the LCA results of the network.

        Returns
        -------
        dict
            Dictionary with the LCA results of the network.
        """
        if not hasattr(self, 'lca'):
            msg = 'No LCA results available. Please run calc_background_impact first.'
            raise hlp.TESPyNetworkError(msg)
        self.impact={}      
        self.impact_allocated={}     
        self.background_flows={}
        for cat in self.method_config['impact_categories']:
            self.impact[cat] = 0
            for comp, _ in self.technosphere_flows.items():
                impact=0
                if not self.get_comp(comp).functional_unit:
                    reference_flow, tespy_component=self.get_reference_flow(comp)
                    impact = self.lca.scores[(cat, comp)] * reference_flow
                    self.impact[cat] += impact * tespy_component.bw_direction
            self.impact_allocated[cat]={}
            if isinstance(self.functional_units, dict):
                for fun, fun_value in self.functional_units.items():
                    func_flow, func_comp=self.get_reference_flow(fun_value['component'].label)
                    self.impact_allocated[cat][fun] =(
                        self.impact[cat] * 
                        fun_value['allocationfactor']/
                        func_flow*fun_value['direction']
                        )
            else:
                msg = ('No reference flow defined. Absolut impact calculated.'
                        'Call: set_functional_unit(functional_unit)' 
                        'to define a reference flow.'      
                )
                raise hlp.TESPyNetworkError(msg)
        return self.impact_allocated

    def get_reference_flow(self, comp):
        reference_flow = 0
        tespy_component= None
        if comp in self.comps['object'].index:
            tespy_component= self.comps.loc[comp]['object']
            if isinstance(tespy_component, Sink):
                reference_flow= tespy_component.inl[0].m.val
                
            elif isinstance(tespy_component, Source):
                reference_flow= tespy_component.outl[0].m.val
            elif isinstance(tespy_component, PowerSource):
                reference_flow= tespy_component.power_outl[0].E.val #in W
            elif isinstance(tespy_component, PowerSink):
                reference_flow= tespy_component.power_inl[0].E.val #in W
        
        elif comp in self.busses.keys():
            tespy_component= self.busses[comp]
            reference_flow= tespy_component.P.val
        else:
            return False
        return reference_flow, tespy_component
        

    def export_bw_dataset(self, database=None):
        pass


class Source(tSource):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction
    
    def set_functional_unit(self,functional_unit=True ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit

class PowerSink(tPowerSink):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction

    def set_functional_unit(self,functional_unit=True ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit

class PowerSource(tPowerSource):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction
    
    def set_functional_unit(self,functional_unit= True):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit

class Sink(tSink):
    def __init__(self, label, **kwargs):
        super().__init__(label, **kwargs)

        self.functional_unit = False
        self.bw_direction = 1

    def link_bw(self, bw_dataset, bw_direction=1):
        self.bw_dataset = bw_dataset
        self.bw_direction= bw_direction

    def set_functional_unit(self,functional_unit=True ):
        """Set the functional unit flag for the component."""
        self.functional_unit = functional_unit
