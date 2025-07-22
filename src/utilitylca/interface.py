import bw2data as bd
import bw2calc as bc
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict, PrivateAttr
from typing import Dict, Union, Optional,Callable
#from bw_interface_schema import models as schema
import datetime
import pint
import warnings



class SimModel(ABC):
    
    @abstractmethod
    def __init__(self, **model_params):
        '''
        Abstract method to init the class. Creates a technosphere dict, wich nedds to be filled by interface class.
        '''
        self.ureg=pint.UnitRegistry()
        self.params= model_params
        
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
    
    def get_technosphere(self):
        return self.technosphere
    
class technosphere_flow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Union[bd.backends.proxies.Activity, SimModel, None]
    target: Union[bd.backends.proxies.Activity, SimModel, None] =None
    amount: Union[pint.Quantity, float,Callable]
    model_unit: Union[pint.Unit, str, None] =None
    comment: Union[str, dict[str, str], None] = None
    description: Union[str, dict[str, str], None] = None
    allocationfactor: Union[float, None]= None
    functional: bool = False
    type: str 
    name: str

class modelInterface(BaseModel, ABC):
    '''class for interface external activity models with brightway25'''
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    model: SimModel
    name: str

    technosphere: Dict[str, technosphere_flow]={}
    elementary_flows: Dict[str, technosphere_flow]={}
    params: Optional[Dict[str, Union[float, int, bool, str]]]=None
    methods: list=[]
    converged: bool= False
    ureg: pint.UnitRegistry=pint.UnitRegistry()
    method_config: Dict={}
    impact_allocated: Dict={}
    impact: dict={}
    lca: Optional[bc.MultiLCA]=None

    def __init__(self, name, model):
        super().__init__(name=name, model=model)
        #self.name = name
        self.technosphere= self.model.get_technosphere()
        self.params = self.model.params

    def update_flows(self):
        for name,flow   in self.technosphere.items():
            name.amount = self.model.technosphere[name].amount

    def setup_link(self):
        if len(self.model.technosphere) != len(self.technosphere):
            raise ValueError("Length of model technosphere matches not the length of ")


        self.technosphere= self.model.link_technosphere(self.technosphere)
        self.elementary_flows= self.model.link_elementary_flows(self.elementary_flows)
        self.functional_unit = self.model.setup_functional_unit()

    def calculate_background_impact(self):
        '''
        Calculate the background impact based on the parameters provided.
        '''
        if self.technosphere is None:
            raise ValueError("technosphere dict not created. Define and call 'link_technosphere' first.")
        
        background_flows={}
        for name, ex in self.technosphere.items():
            if not ex.functional:
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
                
                if ex.functional:
                    continue

                self.impact[cat] += self.lca.scores[(cat, name)]*self._get_flow_value(ex)  
            self.impact_allocated[cat]={}
            #if isinstance(self.functional_unit, dict):
            for name, ex in self.technosphere.items():
                if not ex.functional:
                    continue
                else:
                    self.impact_allocated[cat][name] =(
                        self.impact[cat] * 
                        ex.allocationfactor/self._get_flow_value(ex)
                        )
        return self.impact_allocated
    
    def _get_flow_value(self, ex):
        if callable(ex.amount):
            amount=ex.amount()
        else:
            amount= ex.amount
        # check for unit and transform it in the correct unit if possible.
        
        if isinstance(amount, pint.Quantity):
            try:
                return amount.m_as(ex.source_unit)
            except Exception as e:
                warnings.warn(f"No valid source Unit: {e}. Trying dataset unit instead...",UserWarning)
                try:
                    if ex.target == self.model:
                        return amount.m_as(ex.source.get('unit'))
                    elif ex.source ==self.model:
                        return amount.m_as(ex.target.get('unit'))
                    elif ex.type =='product':
                        return amount.m
                except Exception as e:
                    warnings.warn(f"Even the dataset got no valid source Unit: {e}. Ignore unit transformation.", UserWarning)
                    return amount.m
        elif ex.model_unit!=None and ex.model_unit in self.model.ureg:
            try:
                if ex.target == self.model:
                    return self.model.ureg.Quantity(amount, ex.model_unit).m_as(ex.source.get('unit'))
                elif ex.source ==self.model:
                    return self.model.ureg.Quantity(amount, ex.model_unit).m_as(ex.target.get('unit'))
                elif ex.type =='product':
                    return amount

            except Exception as e:
                    warnings.warn(f"Even the dataset got a valid pint Unit: {e}. Ignore unit transformation.", UserWarning)
                    return amount
        else:
            warnings.warn('no unit check possible. Use pint units if possible or provide pint compatible model unit name.',UserWarning)
            return amount

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
    
