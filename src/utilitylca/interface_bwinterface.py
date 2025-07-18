import abc

import bw_interface_schemas as schema  

class activity_model():
    '''abstract class for activity models in brightway25'''

    def __init__(self, name: str, **params):
        self.name=name
        self.params=params
        self.technosphere = []
        self.biosphere ={}
        self.functional_unit = {}
        self.name = None
        self.software = None
        self.model= None
        self.nodes={self.name: {schema.Process(name= self.name)
        }}
    

    def setup_model(self, **model_params):
        '''
        Abstract class to create a model based on the parameters provided.
        
        '''
        pass

    def calculate_model(self, **model_params):
        '''
        Abstract class to calculate the model based on the parameters provided.
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual recalculation logic
        for key, value in model_params.items():
            self.params[key] = value

    def set_technosphere(self, technosphere: list):
        '''Concrete class to set the technosphere for the model.'''
        for ex in technosphere:
            self.technosphere = schema.QuantitativeEdge(
                edge_type=schema.QuantitativeEdgeTypes.technosphere,
                source= self.name,
                target= None,
                amount=ex,
            )
            

    def link_bw_datasets(self, **bw_datasets):
        '''
        Link the model to Brightway datasets.
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual linking logic
        for key, value in bw_datasets.items():
            self.params[key] = value

    def setup_functional_unit(self, allocation):
        '''
        Set up the functional unit for the model.
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual setup logic
        self.functional_unit = allocation

    def calculate_background_impact(self, **params):
        '''
        Calculate the background impact based on the parameters provided.
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual calculation logic
        impact = 0.0
        for key, value in params.items():
            impact += value
    
    def calculate_impact(self):
        '''
        Calculate the impact
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual impact calculation logic
        impact = 0.0
        for key, value in params.items():
            impact += value
        
        return impact
    
    def export(self, database, activity_name):
        '''
        Export the model to a brightway25 database.
        
        '''
        if self.model is None:
            raise ValueError("Model not created. Call create_model() first.")
        
        # Placeholder for actual export logic
        
        print(f"Model exported to {activity_name}")