import bw2data as bd
import bw2calc as bc
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict
from typing import Dict, Union
#from bw_interface_schema import models as schema
import datetime
import pint
import warnings


class technosphere_flow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Union[bd.backends.proxies.Activity, str]
    target: Union[bd.backends.proxies.Activity, str, None] =None
    amount: Union[pint.Quantity, float]
    source_unit: Union[pint.Unit, str, None] =None
    comment: Union[str, dict[str, str], None] = None
    allocationfactor: Union[float, None]= None

class activity_model(ABC):
    '''abstract class for external activity models for brightway25'''
    #TODO: validation

    def __init__(self, name, **params):
        self.name = name
        self.params=params
        self.technosphere=None
        self.elementary_flows=None
        self.functional_unit=None
        self.model = None
        self.methods=[]
        self.converged=False
        self.initialized = False
        self.ureg = pint.UnitRegistry()

    @abstractmethod
    def init_model(self, **model_params):
        '''
        Abstract method to Create a model based on the parameters provided.
        
        '''
        self.model=None

    @abstractmethod
    def calculate_model(self, **model_params):
        '''
        Abstract method to calculate the model based on the parameters provided.
        
        '''
        pass
    
    @abstractmethod
    def link_technosphere(self, datasets: dict) -> dict:
        '''
       
        Abstract method to Link the model to Brightway datasets. 
        
        Parameters:
        dict of the schema:
        datasets= {model_flow:bw_dataset}

        returns technosphere dict of the schema:
        technosphere= {'model_flow name': {source: bw_dataset,
                            amount: amount_reference,
                            unit: source_pint_unit,
                            description: description of the dataset} }
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        technosphere={}
        return technosphere

    @abstractmethod    
    def link_elementary_flows(self, elementary_flows) -> dict:
        pass
    
    @abstractmethod    
    def setup_functional_unit(self) -> dict:
        '''
        Abstract class to set up the functional unit for the model.
        Returns:
        
        dict of the type:
        {'model_flow_name':{'amount':amount_reference},
                            'allocationfactor':1,
                            'unit': MJ}
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual setup logic
        functional_unit = {}
        return functional_unit

    def setup_link(self, datasets, elementary_flows):
        if self.model is None:
            self.init_model()   

        self.technosphere= self.link_technosphere(datasets)
        self.elementary_flows= self.link_elementary_flows(elementary_flows)
        self.functional_unit = self.setup_functional_unit()

    def calculate_background_impact(self):
        '''
        Calculate the background impact based on the parameters provided.
        '''
        if self.technosphere is None:
            raise ValueError("technosphere dict not created. Define and call 'link_technosphere' first.")
        
        background_flows={}
        for name, ex in self.technosphere.items():
            background_flows[name]= {ex.source.id:1}
        # Placeholder for actual calculation logic
        self.method_config= {'impact_categories':self.methods}

        data_objs = bd.get_multilca_data_objs(background_flows, self.method_config)
        self.lca = bc.MultiLCA(demands=background_flows,
                    method_config=self.method_config, 
                    data_objs=data_objs
                    )
        self.lca.lci()
        self.lca.lcia()
    
    def calculate_impact(self):
        '''
        Calculate the impact
        '''

        if not hasattr(self, 'lca'):
            self.calculate_background_impact()
        # Placeholder for actual impact calculation logic
        self.impact_allocated = {}
        self.impact = {}
        for cat in self.method_config['impact_categories']:
            self.impact[cat] = 0
            for name, ex  in self.technosphere.items():
                impact=0
                if callable(ex.amount):
                    amount=ex.amount()
                else:
                    amount= ex.amount
                # check for unit and transform it in the correct unit if possible.
                if isinstance(amount, pint.Quantity):
                    try:
                        impact =self.lca.scores[(cat, name)] *amount.m_as(ex.source_unit)
                    except Exception as e:
                        warnings.warn(f"No valid source Unit: {e}. Trying dataset unit instead...",UserWarning)
                        try:
                            impact =self.lca.scores[(cat, name)] *amount.m_as(ex.source.get('unit'))
                        except Exception as e:
                            warnings.warn(f"Even the dataset got no valid source Unit: {e}. Ignore unit transformation.")
                            impact = self.lca.scores[(cat, name)]* amount.m
                else:
                    warnings.warn('no unit check possible. Use pint units if possible.')
                    impact = self.lca.scores[(cat, name)]*amount
                self.impact[cat] += impact 
            self.impact_allocated[cat]={}
            if isinstance(self.functional_unit, dict):
                for fun, fun_value in self.functional_unit.items():
                    
                    self.impact_allocated[cat][fun] =(
                        self.impact[cat] * 
                        fun_value.allocationfactor/fun_value.amount.m
                        )
        return self.impact_allocated
    
    def export_to_bw(self, database=None, identifier=None):
        if not hasattr(self, 'impact_allocated'):
            self.calculate_impact()

        if database== None:
            database = f"process_model_db" 

        if database not in bd.databases:
            bd.Database(database).register() 
        
        for fun_key, fun_value in self.functional_unit.items():
            now= datetime.datetime.now()
            if identifier==None:
                code= f'{self.name}_{fun_key}_{now}'

            else:
                code= f'{fun_key}_{identifier}'
            node = bd.Database(database).new_node(
                name= fun_key,
                unit= fun_value['unit'],
                code= code
            )
            node.save()

            for flow, flow_value in self.technosphere.items():

                node.new_exchange(
                    input= flow_value['source'],
                    amount= flow_value['amount'],
                    type = 'technosphere',
                ).save()
            
            node.new_exchange(
                input=node,
                amount= 1,
                type = 'production',
            ).save()
        
        return code