
from tespy.networks import Network
from tespy.connections import  Ref

from simodin import interface as link
from . import steam_network_model as snwm

from CoolProp.CoolProp import PropsSI
import numpy as np 
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram


import copy

class steam_net(link.SimModel):
    reference={ 
        'type': 'misc',
        'key': '',
        'author' :'Hannes Schneider',
        'title'  : 'tba',
        'license': 'tba',
        'location':'',
        'year': '2025',
        'doi': 'tba',
        'url': 'https://github.com/HaSchneider'
        }
    description='This SiModIn model can be used to calculate the temperature dependent impact of process heat from steam.'

    def init_model(self, init_arg=None, **params):
        self.cond_inj = False
        self.trap=False # droplet seperator if steam is not saturated at point of use (due to losses in pipe)
        
        # Steam net properties:
        self.params={
            'needed_temperature':230,
            'makeup_factor':0.05,
            'Tamb':20,
            'leakage_factor':0.075,#https://invenoeng.com/steam-system-thermal-cycle-efficiency-a-important-benchmark-in-the-steam-system/
            'mains':[4,8,16,40],
            'max_pressure':130,
            'heat':40E6, # 40 MW capacity of the pipe
            'wind_velocity':3,
            'insulation_thickness':0.1, #https://doi.org/10.1016/j.applthermaleng.2016.03.010
            'environment_media':'air',
            'pipe_depth':2,
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

        self.converged = False
        self._init_mains()
        #self._calc_mains()
        self.model= Network()
        self.initialized = True


    def calculate_model(self, **params):
        '''
        needed_pressure: steam pressure in bar
        heat: transfered heat in W
        makeup_factor: factor of the amount of make up water default= 0.02 
        net_pressure: steam net pressure in bar
        '''

        self._calc_mains()
        i=0
        while i < 1:
            try:
                snwm.create_steam_net(self)
            except Exception as e:
                print(e)
            else:
                self.converged=True
                self._result()
                break

            i+=1
        else:
            raise Exception('Steam net calculation failed. Check the parameter and try again!')
        
        #self.define_flows()
    
    
    def define_flows(self):
        if not self.converged:
            self.calculate_model()

        self.technosphere={
            'steam generation': link.technosphere_edge(
                name='steam generation',
                source= None,
                target=self,
                amount= lambda:self.model.get_conn("e_boil").E._val*self.model.units.ureg.second ,
                type= link.technosphereTypes.input,
                description= f'Steam generation for high pressure steam of 100 bar in large chemical plants. Without any distribution losses. If distribution losses are assumed in original dataset, correct them in this flow.',
                default_name='heat production, natural gas, at industrial furnace >100kW'
                ),
            'electricity grid':link.technosphere_edge(
                name='electricity grid',
                source= None,
                target=self,
                amount= lambda:self.model.get_conn("e_pump").E._val *self.model.units.ureg.second ,
                type= link.technosphereTypes.input,
                description= 'Electricity from grid, medium voltage.',
                default_name= 'market for electricity, medium'
                ),
            'electricity substitution':link.technosphere_edge(
                name='electricity substitution',
                source= self,
                target= None,
                amount= lambda:-self.model.get_conn("e_turb_grid").E._val*self.model.units.ureg.second ,
                type= link.technosphereTypes.substitution,
                default_name= 'market for electricity, medium'),
            'distributed steam':link.technosphere_edge(
                name='distributed steam',
                source= self,
                target = None,
                amount= lambda:(self.model.get_conn("e_heat_sink").E._val*self.model.units.ureg.second).to('megajoule'),
                functional = True,
                reference = True,
                type= link.technosphereTypes.product,
                allocationfactor=1,
                model_unit='MJ',
                description='Distributed steam at condenser. Incl. distribution losses and multifunctionality due to electricity generation in back pressure turbine taken into account.')
            }

        self.biosphere={'steam leak':link.biosphere_edge(
            name= 'steam leak',
            source= self,
            target= None,
            amount= lambda:(self.model.get_conn("c_leak").m._val*
                     self.model.units.ureg.second).to('tonne').m *self.model.units.ureg('m^3'),
            default_code= '51254820-3456-4373-b7b4-056cf7b16e01'
            )}
        

    def recalculate_model(self, **params):

        self._calc_mains()
        try:
            self.change_parameters()
        except Exception as e:
            raise Exception(e)

        self.converged = False
        try:
            self.model.solve('design')
        except Exception as e:
            raise Exception(e)
        self._result()
        #self.calculate_impact()
        self.converged=True
        self.old_nw = self.model


    def change_parameters(self):
        # makeup_factor:

        c04 = self.model.get_conn('c04')
        c022 = self.model.get_conn('c022')
        muw= self.model.get_conn('muw')
        
        muw2=self.model.get_conn('muw2')

        self.model.get_comp('steam pipe').set_attr(
            Tamb = self.params['Tamb'], 
            L = self.params['pipe_length'],
            insulation_thickness= self.params['insulation_thickness'],
            wind_velocity=self.params['wind_velocity'],
            )
        self.model.get_comp('condensate pipe').set_attr(
            Tamb = self.params['Tamb'], 
            L = self.params['pipe_length'],
            insulation_thickness= self.params['insulation_thickness'],
            wind_velocity=self.params['wind_velocity'],
            )
        
        self.model.get_comp('hex heat sink').set_attr(Q=-self.params['heat'])

        #muw
        muw.set_attr(m=Ref(c04, self.params['makeup_factor'], 0),)
        muw2.set_attr(T= self.params['Tamb'])

        #leakage_factor:
        self.model.get_conn('c_leak').set_attr(m=Ref(c022, self.params['leakage_factor'], 0))

        #needed pressure:
        self.model.get_conn('c01').set_attr(p = self.needed_pressure)

    def _result(self):
        c_leak = self.model.get_conn('c_leak')
        c02 = self.model.get_conn('c02')
        c03 = self.model.get_conn('c03')
        c04 = self.model.get_conn('c04')
        cond_5 = self.model.get_conn('cond_5')
        cond_1 = self.model.get_conn('cond_1')
        c01 = self.model.get_conn('c01')
        c1 = self.model.get_conn('c1')
        muw= self.model.get_conn('muw')
        muw2=self.model.get_conn('muw2')
        
        boiler=self.model.get_conn("e_boil")
        hex_heat_sink=self.model.get_conn("e_heat_sink")
        turbine_grid = self.model.get_conn('e_turb_grid')

        leakage_loss= c_leak.m._val *(c_leak.h._val - muw2.h._val)
        pipe_loss = c02.m._val *c03.h._val - c02.m._val * c02.h._val #only steam pipe
        self.elec_factor= abs(turbine_grid.E._val/hex_heat_sink.E._val).m  
        self.boiler_factor = abs(boiler.E._val/hex_heat_sink.E._val).m
        self.losses=((pipe_loss+leakage_loss)/abs(hex_heat_sink.E._val)).m
        self.watertreatment_factor = abs(muw.m._val/hex_heat_sink.E._val).m
        #calc exergy reduction:
        t_amb= self.model.units.ureg.Quantity(self.params['Tamb'],'degC').to('kelvin')
        self.E_bpt=((c03.h._val -c04.h._val) 
                    - t_amb * (c03.s._val - c04.s._val))* c03.m._val

        if self.cond_inj:
            self.E_hs= ((cond_1.h._val -cond_5.h._val) 
                        - t_amb * (cond_1.s._val - cond_5.s._val))* cond_5.m._val
        else:
            self.E_hs= ((c1.h._val -c01.h._val) 
                        - t_amb * (c1.s._val - c01.s._val))* c01.m._val
        
        self.alloc_ex = (self.E_hs /(self.E_hs + self.E_bpt)).m

    def _calc_pressure(self):
        self.needed_pressure= PropsSI('P','Q',0,'T',self.params['needed_temperature']+273,'IF97::water')*1E-5
        
    def _init_mains(self):
        self.params['mains'].sort()
        self.main_dict={}
        for pres in self.params['mains']:
            self.main_dict[str(pres)] = {}
            self.main_dict[str(pres)]['pressure'] = pres
            self.main_dict[str(pres)]['temperature'] =PropsSI('T', 'P', pres*1E5, 'Q', 1, 'IF97::water') - 273.15 # in °C
            self.main_dict[str(pres)]['impact'] = None
    def _calc_mains(self): 
        self.params['mains'].sort()
        self._calc_pressure()
        s_superheating_max_pressure=  PropsSI('S','P',self.params['mains'][0]*1E5,'Q',1,'IF97::water') 
        self.h_superheating_max_pressure=  PropsSI('H','P',self.params['max_pressure']*1E5,'S',s_superheating_max_pressure,'IF97::water') *1E-3
        if self.needed_pressure*1.05 > self.params['mains'][-1]:
            print('needed pressure larger than net pressure!')
        self.main_pressure = min((x for x in self.params['mains'] if x >= self.needed_pressure*1.01), default=None) 

        for pres in self.params['mains']:
            self.main_dict[str(pres)]['pressure'] = pres
            self.main_dict[str(pres)]['temperature'] =PropsSI('T', 'P', pres*1E5, 'Q', 1, 'IF97::water') - 273.15 # in °C

    def plot_Ts(self):
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
    
