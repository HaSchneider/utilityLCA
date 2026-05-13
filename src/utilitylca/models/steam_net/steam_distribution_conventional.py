
from tespy.networks import Network
from tespy.connections import  Ref
from tespy.models import  template

from simodin import interface as link
from . import steam_network_model as snwm

from CoolProp.CoolProp import PropsSI
import numpy as np 
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram


import copy
import logging

logger = logging.getLogger(__name__)
class steam_net(link.SimModel, template.ModelTemplate):
    """
    Class to implement a steam distribution model for conventional steam networks. The model is based on the
    `SiModIn <https://github.com/HaSchneider/SiModIn>`_ model to calculate the temperature dependent impact of process heat from steam. 
    The model considers physical, dissipative and pressure losses in the steam network.
    
    Parameters
        ----------
        Name : str
            Name of the model.
        **parameter
            Parameters of the model. See parameters section for details.
    
    """

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
    description='This SiModIn model can be used to calculate the temperature dependent impact of process heat from steam. ' \
    'The model considers physical, dissipative and pressure losses in the steam network.' \
    '' \
    
    parameters={
        'needed_temperature':link.parameter(
            name='needed_temperature',
            default=180,
            min=80,
            max=250,
            description='Needed temperature of the steam at the point of use in °C. Must be larger than 100 °C.',),
        'makeup_factor':link.parameter(
            name='makeup_factor',
            default=0.05,
            min=0,
            max=1,
            description='Factor of the amount of make up water. Must be between 0 and 1.',),
        'leakage_factor':link.parameter(
            name='leakage_factor',
            default=0.075,
            min=0,
            max=1,
            description='Factor of the amount of steam leakage. Must be between 0 and 1.',
            reference= 'https://invenoeng.com/steam-system-thermal-cycle-efficiency-a-important-benchmark-in-the-steam-system/'),
        'Tamb':link.parameter(
            name='Tamb',
            default=20,
            min=0,
            max=30,
            description='Ambient temperature in °C. Must be between 0 and 30 °C.',),
        'mains':link.parameter(
            name='mains',
            default=[4,8,16,40],
            description='Main pressures in bar. Must be a list of positive values.',),
        'max_pressure':link.parameter(
            name='max_pressure',
            default=130,
            min=10,
            max=200,
            description='Maximum pressure in bar.',),
        'heat_capacity_pipe_network':link.parameter(
            name='heat_capacity_pipe_network',
            default=20E6,
            description='Heat capacity of the pipe network in W.',),
        'heat':link.parameter(
            name='heat',
            default=1e6,
            description='Transferred heat at process in W.',),
        'wind_velocity':link.parameter(
            name='wind_velocity',
            default=3,
            description='Wind velocity in m/s. Must be a positive value.',),
        'insulation_thickness':link.parameter(
            name='insulation_thickness',
            default=0.1,
            description='Insulation thickness in m. Must be a positive value.',
            reference= 'https://doi.org/10.1016/j.applthermaleng.2016.03.010'),
        'environment_media':link.parameter(
            name='environment_media',
            default='air',
            description='Environment media for heat loss calculation. Must be either "air" or "water".',),
        'pipe_depth':link.parameter(
            name='pipe_depth',
            default=2,
            description='Depth of the pipe in m. Must be a positive value.',),
        'pipe_length':link.parameter(
            name='pipe_length',
            default=1000,
            description='Length of the pipe in m. Must be a positive value.',),
    }
    def _create_network(self) -> None:
        super()._create_network()
        self.cond_inj = False
        self.trap=False # droplet seperator if steam is not saturated at point of use (due to losses in pipe)
        
        self.desuperheat_steam=False

        #self.params= default_params | self.params | params
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
        
        self._validate_params()
        self._calc_mains()

        mains_sorted = sorted(self.params['mains'])
        if self.main_pressure in mains_sorted:
            idx = mains_sorted.index(self.main_pressure)
            next_main = mains_sorted[idx - 1] if idx - 1 >= 0 else 1.013
        else:
            raise ValueError("Main pressure not found in mains list")
        
        self.model= self.nw
        
        snwm.create_steam_net(self)
        self._result()
        self.initialized = True
        
    def _parameter_lookup(self) -> dict:
        #return super()._parameter_lookup()

        return {
            "Tamb": {'set':self._change_Tamb},
            "insulation_thickness":{'set':self._change_insulation},
            "wind_velocity": {'set':self._change_wind},
            "environment_media": {'set':self._change_env},
            "pipe_length": {'set':self._change_length},
            "needed_temperature":{'set':self._change_temp},
            "heat": {'set':self._change_heat},
            "heat_capacity_pipe_network": {'set':self._change_heat},
            "network condensation": ["Components", "a1", "Q"],

            "leakage_factor": {'set':self._change_leakage},
            "max_pressure": ["Connection", "c0_6", "max_pressure"],
            "makeup_factor": {'set':self._change_makeup},
            "max_pressure": ["Connections", "c0_6", "p"],
            #"mains":{'set':self._change_mains},
        }
    
    def _change_temp(self, value):
        self._calc_mains()
        self.model.get_conn('c1_5').set_attr(p= self.main_pressure)
        self.model.get_conn('c0_2').set_attr(p= self.main_pressure)
        self.model.get_conn('c1_1').set_attr(p= self.needed_pressure)
  

    def _change_heat(self, value):
        self.model.get_comp('network condensation').set_attr(
            Q= -(self.params['heat_capacity_pipe_network']-value) )
        self.model.get_comp('hex heat sink').set_attr(Q=-value)

    def _change_heat_capa(self, value):
        self.model.get_comp('network condensation').set_attr(
            Q= -(value-self.params['heat'])            )   

    def _change_makeup(self, value):
        c1_6=self.model.get_conn('c1_6')
        self.model.get_conn('muw').set_attr(m=Ref(c1_6, value, 0))
        self.model.get_conn('c_blowdown').set_attr(m=Ref(c1_6, value, 0))
        
    def _change_leakage(self, value):
        c1_4=self.model.get_conn('c1_4')
        self.model.get_conn('c_leak').set_attr(m=Ref(c1_4, value, 0))

    def _change_Tamb(self, value):
        self.model.get_comp('steam pipe').set_attr(Tamb= value)
        self.model.get_comp('condensate pipe').set_attr(Tamb= value)
        self.model.get_conn('c1_6').set_attr(T=value)
        self.model.get_conn('c_leak').set_attr(T= value)
        self.model.get_conn('muw').set_attr(T= value)
        self.model.get_conn('muw2').set_attr(T= value)

    def _change_insulation(self, value):
        self.model.get_comp('steam pipe').set_attr(insulation_thickness= value)
        self.model.get_comp('condensate pipe').set_attr(insulation_thickness= value)
    
    def _change_wind(self, value):
        self.model.get_comp('steam pipe').set_attr(wind_velocity= value)
        self.model.get_comp('condensate pipe').set_attr(wind_velocity= value)
    
    def _change_env(self,value):
        self.model.get_comp('steam pipe').set_attr(environment_media= value)
        self.model.get_comp('condensate pipe').set_attr(environment_media= value)
    
    def _change_length(self,value):
        self.model.get_comp('steam pipe').set_attr(L= value)
        self.model.get_comp('condensate pipe').set_attr(L= value)

    def init_model(self, init_arg=None):
        """
        Abstract simodin class. Initialising of the model.
        
        """
        
        self._create_network()
        
    
    def _validate_params(self):        
        if self.params['max_pressure'] < self.params['mains'][-1]:
            raise ValueError('max pressure must be larger than the highest main pressure')
        if self.params['heat_capacity_pipe_network'] <self.params['heat']:
            raise ValueError('Heat capacity of the pipe network must be larger than the transferred heat at the heat exchanger')
    
    def calculate_model(self, **params):
        """
        Method to calculate the steam net model.
        """

        self._validate_params()
        self._calc_mains()
        mains_sorted = sorted(self.params['mains'])
        if self.main_pressure in mains_sorted:
            idx = mains_sorted.index(self.main_pressure)
            next_main = mains_sorted[idx - 1] if idx - 1 >= 0 else 1.013
        else:
            raise ValueError("Main pressure not found in mains list")
        i=0
        while i < 3:
            try:
                #snwm.create_steam_net(self)
                print('changed params:', params)
                self.solve_model_design(**params)
            except Exception as e:
                print('did not solve')
                logger.info(f'Calculation failed: {e}')
                raise Exception(f'Calculation failed: {e}')
            else:
                self.converged=True
                self._result()
                break

            i+=1
        else:
            raise Exception('Steam net calculation failed. Check the parameter and try again!')
        
        #self.define_flows()
    
    
    def define_flows(self):
        """
        Define the technosphere and biosphere flows of the model based on the calculated model. 
        """


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
                allocationfactor=lambda:((self.model.get_comp('hex heat sink').Q._val/
                                  (self.model.get_comp('network condensation').Q._val +self.model.get_comp('hex heat sink').Q._val)).m),
                model_unit='MJ',
                description='Distributed steam at condenser. Incl. distribution losses and multifunctionality ' \
                'due to electricity generation in back pressure turbine taken into account.'),
            'network steam':link.technosphere_edge(
                name='network steam',
                source= self,
                target = None,
                amount= lambda:(self.model.get_conn("e_nw_heat_sink").E._val*self.model.units.ureg.second).to('megajoule'),
                functional = True,
                reference = False,
                type= link.technosphereTypes.product,
                allocationfactor=lambda:((self.model.get_comp('network condensation').Q._val/
                                  (self.model.get_comp('network condensation').Q._val +self.model.get_comp('hex heat sink').Q._val)).m),
                model_unit='MJ',
                description='Distributed steam at network.')
            
            }

        self.biosphere={'steam leak':link.biosphere_edge(
            name= 'steam leak',
            source= self,
            target= None,
            amount= lambda:(self.model.get_conn("c_leak").m._val*
                     self.model.units.ureg.second).to('tonne').m *self.model.units.ureg('m^3'),
            default_code= '51254820-3456-4373-b7b4-056cf7b16e01'
            )}
        

    def _result(self):
        c_leak = self.model.get_conn('c_leak')
        c1_4 = self.model.get_conn('c1_4')
        c1_5 = self.model.get_conn('c1_5')
        c1_6 = self.model.get_conn('c1_6')
        
        c1_1 = self.model.get_conn('c1_1')
        c0_2 = self.model.get_conn('c0_1')
        c0_3 = self.model.get_conn('c0_3')
        muw= self.model.get_conn('muw')
        muw2=self.model.get_conn('muw2')
        
        boiler=self.model.get_conn("e_boil")
        hex_heat_sink=self.model.get_conn("e_heat_sink")
        net_heat_sink=self.model.get_conn("e_nw_heat_sink")
        turbine_grid = self.model.get_conn('e_turb_grid')

        leakage_loss= c_leak.m._val *(c_leak.h._val - muw2.h._val)
        pipe_loss = self.model.get_conn('e_pi_sink').E._val 
        #(abs(c1_4.m._val *c1_5.h._val - c1_4.m._val * c1_4.h._val )
        #            + abs(c0_2.m._val * c0_2.h._val - c0_3.m._val * c0_3.h._val)
        #)
        self.elec_factor= abs((turbine_grid.E._val/hex_heat_sink.E._val).to_base_units().m )
        self.boiler_factor = abs((boiler.E._val/hex_heat_sink.E._val).to_base_units().m)
        self.diss_losses=(abs(pipe_loss)/
                     (abs(boiler.E._val)-abs(self.model.get_conn('e_turb').E._val)+self.model.get_conn('e_pump').E._val)
                     ).to_base_units().m
        self.leak_losses=(abs(leakage_loss)/
                     (abs(boiler.E._val)-abs(self.model.get_conn('e_turb').E._val)+self.model.get_conn('e_pump').E._val)
                     ).to_base_units().m
        
        self.losses=1-(
            (self.model.get_conn('e_heat_sink').E._val + 
             self.model.get_conn('e_nw_heat_sink').E._val
             )/
            (self.model.get_conn('e_boil').E._val- self.model.get_conn('e_turb').E._val +self.model.get_conn('e_pump').E._val) 
            )
        
        self.watertreatment_factor = abs(muw.m._val/hex_heat_sink.E._val).m
        #calc exergy reduction:
        t_amb= self.model.units.ureg.Quantity(self.params['Tamb'],'degC').to('kelvin')
        self.E_bpt=((c1_5.h._val -c1_6.h._val) 
                    - t_amb * (c1_5.s._val - c1_6.s._val))* c1_5.m._val

        if self.cond_inj:
            cond_5 = self.model.get_conn('cond_5')
            cond_1 = self.model.get_conn('cond_1')
            self.E_hs= ((cond_1.h._val -cond_5.h._val) 
                        - t_amb * (cond_1.s._val - cond_5.s._val))* cond_5.m._val
        else:
            self.E_hs= ((c0_2.h._val -c1_1.h._val) 
                        - t_amb * (c0_2.s._val - c1_1.s._val))* c1_1.m._val
        self.E_nw_hs= ((self.model.get_conn('cnw2').h._val -self.model.get_conn('cnw1').h._val) 
                        - t_amb * (self.model.get_conn('cnw2').s._val - self.model.get_conn('cnw1').s._val))* self.model.get_conn('cnw1').m._val
        
        self.alloc_ex = (self.E_bpt /(self.E_hs + self.E_bpt + self.E_nw_hs)).m

    def _calc_pressure(self, temp=None):
        if temp==None:
            temp=self.params['needed_temperature']+273
        else:
            temp= temp+273
        self.needed_pressure= PropsSI('P','Q',0,'T',temp,'IF97::water')*1E-5
        
    def _init_mains(self):
        self.params['mains'].sort()
        self.main_dict={}
        for pres in self.params['mains']:
            self.main_dict[str(pres)] = {}
            self.main_dict[str(pres)]['pressure'] = pres
            self.main_dict[str(pres)]['temperature'] =PropsSI('T', 'P', pres*1E5, 'Q', 1, 'IF97::water') - 273.15 # in °C
            self.main_dict[str(pres)]['impact'] = None
    def _calc_mains(self, temp=None): 
        self.params['mains'].sort()
        self._calc_pressure(temp)
        s_superheating_max_pressure=  PropsSI('S','P',self.params['mains'][0]*1E5,'Q',1,'IF97::water') 
        self.h_superheating_max_pressure=  PropsSI('H','P',self.params['max_pressure']*1E5,'S',s_superheating_max_pressure,'IF97::water') *1E-3
        if self.needed_pressure*1.02 > self.params['mains'][-1]:
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
    
