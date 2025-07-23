import bw2data as bd
import bw2calc as bc
from abc import ABC, abstractmethod
from pydantic import BaseModel, ConfigDict
from typing import Dict, Union, Optional,Callable
import datetime
import pint
import warnings

class SimModel(ABC):
    def __init__(self, name, **model_params):
        self.name = name
        self.ureg=pint.UnitRegistry()
        self.params= model_params
        self.technosphere={}
        self.location = 'GLO'
    
    @abstractmethod
    def init_model(self, **model_params):
        '''
        Abstract method to initiate the model. 
        '''
        
        self.params= model_params

    @abstractmethod
    def calculate_model(self, **model_params):
        '''
        Abstract method to calculate the model based on the parameters provided.
        '''
        pass

    @abstractmethod
    def recalculate_model(self, **model_params):
        '''
        Abstract method to recalculate the model based on the parameters provided.
        '''
        pass

    @abstractmethod
    def set_technosphere(self) -> dict:
        '''
        Abstract method to define the model technosphere flows. 
        Creates a technosphere dict, wich nedds to be filled by interface class with brightway datasets.

        Returns:
        Dict of the schema:
        technosphere= {'model_flow name': technosphere_flow }
        '''
        
        self.technosphere={}
        
    
    @abstractmethod    
    def set_elementary_flows(self) -> dict:
        '''
        Abstract method to define the model biosphere flows. 
        
        Returns:
        Dict of the schema:
        biosphere= {'model_flow name': biosphere_flow }
        '''
        pass
    
    def get_technosphere(self):
        '''
        Method to get the current technosphere dict. 
        Needs to be executed when the model gets recalculated and no callable objects are used.
        
        '''
        
        return self.technosphere
    
class technosphere_flow(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    source: Union[bd.backends.proxies.Activity, SimModel, None]
    target: Union[bd.backends.proxies.Activity, SimModel, None] =None
    amount: Union[pint.Quantity, float,Callable]
    model_unit: Union[pint.Unit, str, None] =None
    dataset_unit: Union[pint.Unit, str, None] =None
    comment: Union[str, dict[str, str], None] = None
    description: Union[str, dict[str, str], None] = None
    allocationfactor: float= 1.0
    functional: bool = False
    type: str 
    name: str

class modelInterface(BaseModel):
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
        self.ureg = self.model.ureg

    def update_flows(self):
        for name,flow   in self.technosphere.items():
            name.amount = self.model.technosphere[name].amount

    def setup_link(self):
        if len(self.model.technosphere) != len(self.technosphere):
            raise ValueError("Length of model technosphere matches not the length of ")

        self.technosphere= self.model.set_technosphere()
        self.elementary_flows= self.model.set_elementary_flows()

    def calculate_background_impact(self):
        '''
        Calculate the background impact based on the parameters provided.
        '''
        if self.technosphere is None:
            raise ValueError("technosphere dict not created. Define and call 'link_technosphere' first.")
        
        background_flows={}
        for name, ex in self.technosphere.items():
            if not ex.functional:
                if ex.source == self.model:
                    background_flows[name]= {ex.target.id:1}    
                else:
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
        #get dataset unit:
        if  ex.target!= None:
            if ex.dataset_unit != None:
                dataset_unit= ex.dataset_unit
            elif ex.target == self.model and 'unit' in ex.source:
                dataset_unit=ex.source.get('unit')
            elif ex.source == self.model and 'unit' in ex.target:
                dataset_unit=ex.target.get('unit')
            else:
                raise ValueError(f'No dataset unit available for {ex.name}.')
        else:
            dataset_unit= 'NaU'
        #get model flow unit:
        if isinstance(amount, pint.Quantity) and dataset_unit in self.model.ureg:
            return amount.m_as(dataset_unit)
        elif isinstance(amount, pint.Quantity) and dataset_unit not in self.model.ureg:
            if dataset_unit != ' ':
                warnings.warn(f"The dataset of {ex.name} got no valid Pint Unit. Ignore unit transformation.", UserWarning)
            return amount.m
        # if no pint quantity                
        elif ex.model_unit!=None and ex.model_unit in self.model.ureg:
            if  ex.target!= None:
                if ex.target == self.model:
                    return self.model.ureg.Quantity(amount, ex.model_unit).m_as(ex.source.get('unit'))
                elif ex.source ==self.model:
                    return self.model.ureg.Quantity(amount, ex.model_unit).m_as(ex.target.get('unit'))
                elif ex.type =='product':
                    return amount
            else:
                return amount
        elif ex.model_unit!=None and ex.model_unit not in self.model.ureg:
            warnings.warn(f"The model flow  of {ex.name} got no valid Pint Unit. Ignore unit transformation.", UserWarning)
            return amount
        else:
            warnings.warn('No unit check possible for {ex.name}. Use pint units if possible or provide pint compatible model unit name.',UserWarning)
            return amount

    def export_to_bw(self, database=None, identifier=None):
        #TODO add biosphere flows
        if not hasattr(self, 'impact_allocated'):
            self.calculate_impact()

        if database== None:
            database = f"simulation_model_db" 

        if database not in bd.databases:
            bd.Database(database).register() 
        
        for fun_name, fun_ex in self.technosphere.items():
            if fun_ex.functional:
                now= datetime.datetime.now()
                if identifier==None:
                    code= f'{self.name}_{fun_name}_{now}'

                else:
                    code= f'{fun_name}_{identifier}'
                node = bd.Database(database).new_node(
                    name= fun_name,
                    unit= fun_ex.model_unit,
                    code= code
                )
                node.save()

                for name, ex in self.technosphere.items():
                    if not ex.functional:
                        allocated_amount= (self._get_flow_value(ex)*
                                           fun_ex.allocationfactor / 
                                           self._get_flow_value(fun_ex))
                        if ex.target == self.model:
                            node.new_exchange(
                                input= ex.source,
                                amount=allocated_amount,
                                type = 'technosphere',
                            ).save()
                        elif ex.source == self.model:
                            node.new_exchange(
                                input= ex.target,
                                amount=allocated_amount,
                                type = 'technosphere',
                            ).save()
                node.new_exchange(
                    input=node,
                    amount= 1,
                    type = 'production',
                ).save()
        
        return code
    
