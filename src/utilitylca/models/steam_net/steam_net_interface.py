
from tespy.networks import Network
from tespy.connections import  Ref

#from tespy.components.piping.pipe_group import Pipe_group
from ... import interface as link
from . import steam_network_model_interface as snwm

from CoolProp.CoolProp import PropsSI
import numpy as np 
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram

# [ ] steam in kg 
# [ ] add function to get impact per main
import copy

class steam_net(link.SimModel):

    def __init__(self,  **params):
        super().__init__()
        # convergence flags:
        self.cond_inj = False
        self.trap=False # droplet seperator if steam is not saturated at point of use (due to losses in pipe)
        
        # Steam net properties:
        self.params={
            'needed_temperature':270,
            'makeup_factor':0.05,
            'Tamb':20,
            'leakage_factor':0.075,#https://invenoeng.com/steam-system-thermal-cycle-efficiency-a-important-benchmark-in-the-steam-system/
            'mains':[4,8,16,40],
            'max_pressure':100,
            'heat':1E6,
            'wind_velocity':2,
            'insulation_thickness':0.1,
            'environment_media':'air',
            'pipe_length':1000,
        } | params

        self.main_pressure = 0
        self.h_superheating_max_pressure = 0
        
        # result properties:
        self.elec_factor =0
        self.boiler_factor =0
        self.losses=0
        self.alloc_ex=0
        self.E_bpt =0
        self.E_hs=0

        self.impact_category = None

    #def init_model(self, **params):
        print(self.params)
        self.converged = False
        self.init_mains()
        self.calc_mains()
        self.model= Network()
        self.initialized = True
        #return self.calculate_impact(allocate)
        self.technosphere={}
        #self.set_technosphere()

    def calculate_model(self, **params):
        '''
        needed_pressure: steam pressure in bar
        heat: transfered heat in W
        makeup_factor: factor of the amount of make up water default= 0.02 
        net_pressure: steam net pressure in bar
        '''
        for p in params:
            self.params[p] =params[p]
        
        i=0
        while i < 1:
            try:
                snwm.create_steam_net(self)
            except:
                pass
            if self.model.converged:
                break
            else:
                #self.model.get_comp('hex heat sink').set_attr(Q=-1E9)
                #self.model= Network()
                old_heat=self.params['heat']
                self.params['heat']=1E9
                snwm.create_steam_net(self)
                self.params['heat']=old_heat
                self.model.get_comp('hex heat sink').set_attr(Q=-self.params['heat'])
                
                self.model.solve('design')
            if self.model.converged:
                break

            i+=1
        else:
            raise Exception('Steam net calculation failed. Please give it another try!')
           
        self.result()

        self.converged=True
    def set_technosphere(self):
        if not self.converged:
            self.calculate_model()

        self.technosphere={
            'steam generation': link.technosphere_flow(
                name='steam generation',
                source= None,
                target=self,
                amount= self.model.get_conn("e_boil").E.val,
                type= 'input'),
            'electricity grid':link.technosphere_flow(
                name='electricity grid',
                source= None,
                target=self,
                amount= self.model.get_conn("e_pump").E.val,
                type= 'input'),
            'electricity substitution':link.technosphere_flow(
                name='electricity substitution',
                source= self,
                target= None,
                amount= -self.model.get_conn("e_turb_grid").E.val,
                type= 'substitution'),
            'distributed steam':link.technosphere_flow(
                name='distributed steam',
                source= self,
                target = None,
                amount=self.model.get_conn("e_heat_sink").E.val,
                functional = True,
                type= 'product',
                allocationfactor=1,
                model_unit='MJ')
            } 
    def link_technosphere(self):
        pass
    
    def link_elementary_flows(self, elementary_flows):
        return {}

    def setup_functional_unit(self):
        
        # Placeholder for actual setup logic
        functional_unit = {'distributed steam':{
            'amount':self.model.get_conn("e_heat_sink").E.val,
            'allocationfactor':1,
            'unit':'MJ'}
        }
        return functional_unit


    def recalculate_steam_net(self, **params):
        for p in params:
            self.params[p] =params[p]
        self.calc_mains()
        self.change_parameters()
        if not self.converged:
            self.model = self.old_nw
        
        self.converged = False
        try:
            self.model.solve('design')
        except:
            return np.nan 
        self.result()
        #self.calculate_impact()
        self.converged=True
        self.old_nw = self.model

        return self.technosphere

    def result(self):
        # TODO check allocation by exergy
        c_leak = self.model.get_conn('c_leak')
        c02 = self.model.get_conn('c02')
        c03 = self.model.get_conn('c03')
        cond_5 = self.model.get_conn('cond_5')
        cond_1 = self.model.get_conn('cond_1')
        c01 = self.model.get_conn('c01')
        c1 = self.model.get_conn('c1')
        muw= self.model.get_conn('muw')
        muw2=self.model.get_conn('muw2')
        
        boiler=self.model.get_conn("e_boil")
        hex_heat_sink=self.model.get_conn("e_heat_sink")
        turbine_grid = self.model.get_conn('e_turb_grid')

        leakage_loss= c_leak.m.val *(c_leak.h.val - muw2.h.val)
        pipe_loss = c02.m.val *c03.h.val - c02.m.val * c02.h.val #only steam pipe
        self.elec_factor= abs(turbine_grid.E.val/hex_heat_sink.E.val)  # *0.9 efficiency of generator
        self.boiler_factor = abs(boiler.E.val/hex_heat_sink.E.val)
        self.losses=(pipe_loss+leakage_loss)/abs(hex_heat_sink.E.val)*1000 #boiler.Q.val+heat_sink.Q.val+bpt.P.val # 
        self.watertreatment_factor = abs(muw.m.val/hex_heat_sink.E.val)
        #calc exergy reduction:
        
        self.E_bpt= turbine_grid.E.val#((c04.h.val*1000 -c03.h.val*1000) - self.params['Tamb']* (c03.s.val - c04.s.val) )* c03.m.val
        if self.cond_inj:
            self.E_hs= ((cond_5.h.val*1000 -cond_1.h.val*1000) - (self.params['Tamb']+273)* (cond_5.s.val - cond_1.s.val))* cond_5.m.val
        else:
            self.E_hs= ((c01.h.val*1000 -c1.h.val*1000) - (self.params['Tamb']+273)* (c01.s.val - c1.s.val))* c01.m.val
        
        self.alloc_ex = self.E_hs /(self.E_hs + self.E_bpt)

    def calc_pressure(self):
        self.needed_pressure= PropsSI('P','Q',0,'T',self.params['needed_temperature']+273,'IF97::water')*1E-5
        #needed_enthalpy= PropsSI('H','Q',0,'T',self.params['needed_temperature']+273,'IF97::water')
        
    def init_mains(self):
        self.params['mains'].sort()
        self.main_dict={}
        for pres in self.params['mains']:
            self.main_dict[str(pres)] = {}
            self.main_dict[str(pres)]['pressure'] = pres
            self.main_dict[str(pres)]['temperature'] =PropsSI('T', 'P', pres*1E5, 'Q', 1, 'IF97::water') - 273.15 # in °C
            self.main_dict[str(pres)]['impact'] = None
    def calc_mains(self): 
        self.params['mains'].sort()
        self.calc_pressure()
        s_superheating_max_pressure=  PropsSI('S','P',self.params['mains'][0]*1E5,'Q',1,'IF97::water') 
        self.h_superheating_max_pressure=  PropsSI('H','P',self.params['max_pressure']*1E5,'S',s_superheating_max_pressure,'IF97::water') *1E-3
        if self.needed_pressure*1.05 > self.params['mains'][-1]:
            print('needed pressure larger than net pressure!')
        self.main_pressure = min((x for x in self.params['mains'] if x >= self.needed_pressure*1.01), default=None) 
        #print(f'self.main_pressure: {self.main_pressure}', f'self.needed_pressure: {self.needed_pressure}')
        #self.main_dict={}
        for pres in self.params['mains']:
            #self.main_dict[str(pres)] = {}
            self.main_dict[str(pres)]['pressure'] = pres
            self.main_dict[str(pres)]['temperature'] =PropsSI('T', 'P', pres*1E5, 'Q', 1, 'IF97::water') - 273.15 # in °C

    def plot_hs(self):
        # Initial Setup
        diagram = FluidPropertyDiagram('water')
        diagram.set_unit_system(T='°C', p='bar', h='kJ/kg')

        # Storing the model result in the dictionary
        result_dict = {}
        result_dict.update(
            {cp.label: cp.get_plotting_data()[1] for cp in self.model.comps['object']
            if cp.get_plotting_data() is not None})

        # Iterate over the results obtained from TESPy simulation
        for key, data in result_dict.items():
            # Calculate individual isolines for T-s diagram
            result_dict[key]['datapoints'] = diagram.calc_individual_isoline(**data)

        # Create a figure and axis for plotting T-s diagram
        fig, ax = plt.subplots(1, figsize=(20, 10))
        isolines = {
            'Q': np.linspace(0, 1, 2),
            'p': np.array([1, 2, 5, 10, 20, 50, 100, 300]),
            'v': np.array([]),
            'h': np.arange(500, 3501, 500)
        }

        # Set isolines for T-s diagram
        diagram.set_isolines(**isolines)
        diagram.calc_isolines()

        # Draw isolines on the T-s diagram
        diagram.draw_isolines(fig, ax, 'Ts', x_min=1000, x_max=8000, y_min=20, y_max=600)

        # Adjust the font size of the isoline labels
        for text in ax.texts:
            text.set_fontsize(10)

        # Plot T-s curves for each component
        for key in result_dict.keys():
            datapoints = result_dict[key]['datapoints']
            _ = ax.plot(datapoints['s'], datapoints['T'], color='#ff0000', linewidth=2)
            _ = ax.scatter(datapoints['s'][0], datapoints['T'][0], color='#ff0000')

        # Set labels and title for the T-s diagram
        ax.set_xlabel('Entropy, s in J/kgK', fontsize=16)
        ax.set_ylabel('Temperature, T in °C', fontsize=16)
        ax.set_title('T-s Diagram of steam net', fontsize=20)

        # Set font size for the x-axis and y-axis ticks
        ax.tick_params(axis='x', labelsize=12)
        ax.tick_params(axis='y', labelsize=12)
        plt.tight_layout()
        return fig
    
    def change_parameters(self):
        # makeup_factor:

        c04 = self.model.get_conn('c04')
        c022 = self.model.get_conn('c022')
        muw= self.model.get_conn('muw')
        muw.set_attr(m=Ref(c04, self.params['makeup_factor'], 0))
        muw2=self.model.get_conn('muw2')

        #Tamb:
        
        self.model.get_comp('steam pipe').set_attr(Tamb = self.params['Tamb'], 
                                                        L = self.params['pipe_length'],
                                                        insulation_thickness= self.params['insulation_thickness'],
                                                        wind_velocity=self.params['wind_velocity'])
        self.model.get_comp('condensate pipe').set_attr(Tamb = self.params['Tamb'], 
                                                        L = self.params['pipe_length'],
                                                        insulation_thickness= self.params['insulation_thickness'],
                                                        wind_velocity=self.params['wind_velocity'])
        
        self.model.get_comp('hex heat sink').set_attr(Q=-self.params['heat'])

        
        #muw.set_attr(T= self.Tamb)
        #muw2
        muw2.set_attr(T= self.params['Tamb'])

        #leakage_factor:
        self.model.get_conn('c_leak').set_attr(m=Ref(c022, self.params['leakage_factor'], 0))

        #needed pressure:
        self.model.get_conn('c01').set_attr(p = self.needed_pressure)
