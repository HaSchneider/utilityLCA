
from tespy.networks import Network
from tespy.components import (
    #DiabaticCombustionChamber, Compressor, HeatExchanger, Condenser,
    Turbine, Source, Sink, Pump, 
    Pipeline, Pipe, CycleCloser, SimpleHeatExchanger, Valve, Merge, Splitter, Drum,
    DropletSeparator
)
#from tespy.components.piping.pipe_group import Pipe_group

from tespy.connections import Connection, Ref, Bus
from CoolProp.CoolProp import PropsSI
import numpy as np 
import matplotlib.pyplot as plt
from fluprodia import FluidPropertyDiagram
from tespy.tools.fluid_properties.wrappers import IAPWSWrapper

from tespy.tools import ExergyAnalysis, helpers
from tespy.tools.helpers import get_chem_ex_lib
import bw2io as bi
import bw2data as bd
import bw2calc as bc
import datetime
import copy
# [ ] steam in kg 


class steam_net:


    def __init__(self):
        self.cond_inj = False
        self.trap=False # droplet seperator if steam is not saturated at point of use (due to losses in pipe)
        self.nw = Network()
        self.old_nw = Network()
        self.makeup_factor=0.05 # also known as condensate return factor. 
        self.Tamb=20
        self.leakage_factor=0.075 #https://invenoeng.com/steam-system-thermal-cycle-efficiency-a-important-benchmark-in-the-steam-system/
        self.mains=[4,8, 16, 40]
        self.max_pressure =100
        self.impact_heat = 0.115634 # kg co2/ MJ   Wärme-Prozess-mix-DE-Chem-Industrie-brutto-2000 
        self.impact_elec = 0.110173 # kg co2/ MJ  Netz-el-DE-Verbund-HS-2020 
        #self.impact_heat_ei= 0.11225 # kg co2 /MJ steam production, as energy carrier, in chemical industry
        #self.impact_elec_ei = 0.11797 # kg co2 /MJ market for electricity, high voltage DE
        self.elec_factor =0
        self.boiler_factor =0
        self.losses=0
        self.alloc_ex=0
        self.E_bpt =0
        self.E_hs=0
        #steam net data:
        self.wind_velocity=10
        self.insulation = 0.1
        self.environment_media = 'air'
        self.pipe_length = 1000 # in m
        self.sections =10
        self.needed_pressure = 0
        self.main_pressure = 0
        self.h_superheating_max_pressure = 0
        self.heat=0
        
        # LCA:
        self.bw_heat = None
        self.bw_electricity = None
        self.bw_water_treatment = None
        self.impact_category = None
        self.net_lca = None
        
        self.converged =False
        self.dataset_correction =1#correction factor if bw dataset already include steam net losses
        self.initialized = False

    def calc_steam_net(self):
        '''
        needed_pressure: steam pressure in bar
        heat: transfered heat in W
        makeup_factor: factor of the amount of make up water default= 0.02 
        net_pressure: steam net pressure in bar
        '''
        self.cond_inj = False
        self.trap=False
        self.converged =False

        self.nw = Network()
        self.nw.set_attr(iterinfo=False)
        self.nw.set_attr(T_unit='C', p_unit='bar', h_unit='kJ / kg')
        boiler = SimpleHeatExchanger('steam boiler' , dissipative=False)
        bpt = Turbine('back pressure turbine')
        pipe_warm =  Pipeline('steam pipe', dissipative=True)
        cond_trap= DropletSeparator('condensate trap')
        valve = Valve('controlvalve')
        heat_sink = SimpleHeatExchanger('heat sink', dissipative=False)
        pipe_cold= Pipeline('condensate pipe',dissipative=True)
        feed_pump= Pump('feedpump')
        cycl=CycleCloser('CycleCloser')
        
        steam_sink = Sink('steam losses')
        steam_leak= Splitter("steam leak")
        makeup_leak =Source('leak makeup')
        makeup_trap =Source('trap makeup')
        makeup=Source("Make-up water")
        blowdown= Sink("blowdown wastewater")
        cond_waste= Sink("pipe condensate wastewater")
        merge = Merge("Makeup water feed", num_in=3)
        merge_injection = Merge("Injection")
        split= Splitter("remove wastewater")

        condensate_split= Splitter("split condensate")
        condensate_drum= Drum('condensate injection drum')
        condensate_sink = Sink('sink 1')
        
        dummy_sink2= Sink('dummy sink2')
        injection_source =Source('injection_source')

        c05 = Connection(cycl, 'out1', boiler, 'in1')
        c04 = Connection(boiler, 'out1', bpt, 'in1')
        c03 = Connection(bpt, 'out1', pipe_warm, 'in1')
        c022= Connection(pipe_warm, 'out1', steam_leak, 'in1')
        c02 = Connection(steam_leak, 'out1', valve, 'in1')

        c_leak = Connection(steam_leak, 'out2', steam_sink, 'in1')
        muw2 = Connection(makeup_leak, 'out1', merge, 'in3')

        c01= Connection(valve, 'out1', heat_sink, 'in1')
        c1 = Connection(heat_sink, 'out1', pipe_cold, 'in1')
        c2 = Connection(pipe_cold, 'out1', split, 'in1')
        c3 = Connection(split, 'out1', merge, 'in1')
        c4 = Connection(merge, 'out1', feed_pump, 'in1')
        c5 = Connection(feed_pump, 'out1', cycl, 'in1')

        muw = Connection(makeup, 'out1', merge, 'in2')
        wawa = Connection(split, 'out2', blowdown, 'in1')

        self.nw.add_conns(c05, c04, c03, c022, c02, c01, 
                    c_leak, 
                    c1, c2, c3, c4, c5, 
                    muw, wawa, muw2)
        
        boiler.set_attr(pr = 1)
        c04.set_attr(fluid={"H2O": 1}, #fluid_engines={"H2O": IAPWSWrapper}, 
                     h= self.h_superheating_max_pressure)#Td_bp=100)
        c05.set_attr(p0=self.main_pressure,m0=self.heat/2700E3 )
        bpt.set_attr(eta_s = 0.85, )
        c03.set_attr(p=self.main_pressure, h0=self.h_superheating_max_pressure, m0=self.heat/2700E3)
        pipe_warm.set_attr(pr=0.95, 
            Tamb = self.Tamb, 
            #kA= 300,
            L=self.pipe_length, 
            D='var',  
            ks=4.57e-5,
            insulation_thickness=self.insulation ,insulation_tc= 0.035, pipe_thickness=0.004,material='Steel', 
            wind_velocity=self.wind_velocity, environment_media = self.environment_media
                ) 
        c_leak.set_attr(m=Ref(c022, self.leakage_factor, 0))
        c01.set_attr(p = self.needed_pressure,h0=self.h_superheating_max_pressure, m0=self.heat/2700E3)#T=needed_temperature +5,

        heat_sink.set_attr(pr=1,Q=-self.heat)
        c1.set_attr(x=0,p0=self.needed_pressure,m0=self.heat/2700E3 )
        pipe_cold.set_attr(pr=0.95, 
            Tamb = self.Tamb, #kA= 300,
            L=self.pipe_length, D='var',  ks=4.57e-5,
            insulation_thickness=self.insulation ,insulation_tc= 0.035, 
            pipe_thickness=0.004,material='Steel', 
            wind_velocity= self.wind_velocity, environment_media = self.environment_media
                )
        feed_pump.set_attr(eta_s =0.9)

        c4.set_attr(p0=self.needed_pressure,m0=self.heat/2700E3 )
        
        c5.set_attr(p=self.max_pressure, h0=self.h_superheating_max_pressure,m0=self.heat/2700E3 )

        muw.set_attr(m=Ref(c04, self.makeup_factor, 0), 
                     T=self.Tamb,
                     fluid={"H2O": 1}, 
                     #fluid_engines={"H2O": IAPWSWrapper}, 
                     p0=self.needed_pressure)
        muw2.set_attr(m=Ref(c_leak, 1, 0), 
                      T=self.Tamb,
                      fluid={"H2O": 1}, 
                      #fluid_engines={"H2O": IAPWSWrapper},
                      p0=self.needed_pressure)
        
        wawa.set_attr(m=Ref(c04, self.makeup_factor, 0))
        
        # bus definition:
        
        fuel_bus = Bus('boiler bus')
        fuel_bus.add_comps({'comp':boiler, 'base':'bus'})
        
        turbine_bus = Bus('turbines')
        turbine_bus.add_comps({'comp': bpt, 'base':'component','char': 0.97})

        pipe_emission =Bus('pipe losses')
        
        pipe_emission.add_comps({'comp':pipe_cold,'char': 1},
                            {'comp':pipe_warm,'char': 1})
        
        pipe_fugitive_emission = Bus('fugitive emission')
        pipe_fugitive_emission.add_comps({'comp': steam_sink,'base':'component'})
        
        product_bus =Bus('heat bus')
        product_bus.add_comps({'comp':heat_sink, 'char': 1},
                            )

        pump_bus = Bus('feedpump bus')
        pump_bus.add_comps({'comp':feed_pump, 'base':'bus'})

        makeup_bus= Bus('makeup water')
        makeup_bus.add_comps({'comp':makeup, 'base':'bus'},
                            {'comp':makeup_leak, 'base':'bus'},
                            )
        blowdown_bus=Bus('blowdown bus')
        blowdown_bus.add_comps({'comp':blowdown, 'base':'component'})
        #overall distribution losses of 20%: https://www.energy.gov/eere/iedo/manufacturing-energy-and-carbon-footprints-2018-mecs
        
        self.nw.add_busses(turbine_bus, 
                    fuel_bus, 
                    product_bus, 
                    pipe_emission, 
                    #pipe_fugitive_emission,
                    makeup_bus,
                    blowdown_bus,
                    pump_bus)
        self.nw.solve('design')
    
        #2. Run: 
        muw.set_attr(T=None)
        muw.set_attr(T=Ref(c2, 1, -20))
        
        #self.nw.solve('design')

        #3. Run: implement condensate injection:
        if c022.x.val ==-1:
            self.nw.del_conns(c01, c1)
            c01= Connection(valve, 'out1', merge_injection, 'in1')
            cond_3 = Connection(injection_source, 'out1', merge_injection, 'in2')
            #cond_4 = Connection(condensate_injection, 'out1', condensate_drum, 'in1')
            cond_5 = Connection(merge_injection, 'out1', heat_sink, 'in1')

            #cond_6 = Connection(condensate_drum, 'out1', condensate_sink, 'in1')
            cond_1 = Connection(heat_sink, 'out1', condensate_split, 'in1')
            cond_2 = Connection(condensate_split, 'out2', dummy_sink2, 'in1')
            c1 = Connection(condensate_split, 'out1', pipe_cold, 'in1')
            self.nw.add_conns(cond_1, cond_2, cond_3,cond_5,c01,c1)

            c01.set_attr(p = self.needed_pressure)
            cond_1.set_attr(x=0)
            c1.set_attr(m=Ref(c01,1,0))
            cond_3.set_attr(x=0, fluid={"H2O": 1}, )#fluid_engines={"H2O": IAPWSWrapper})
            cond_5.set_attr(x=1)
            #cond_6.set_attr(m=0)
            self.nw.solve('design')
            self.cond_inj =True
        
        elif 0< c022.x.val <1:
            merge.set_attr(num_in=4)
            self.nw.del_conns(c02)
            muw3 = Connection(makeup_trap, 'out1', merge, 'in4')
            c023= Connection(steam_leak, 'out1', cond_trap, 'in1')
            c024= Connection(cond_trap, 'out2', valve, 'in1')
            c_trap_waste = Connection(cond_trap, 'out1', cond_waste, 'in1')
            
            self.nw.add_conns(c023, c024, c_trap_waste, muw3)

            muw3.set_attr(m=Ref(c_trap_waste, 1, 0), T=self.Tamb,fluid={"H2O": 1}, )#fluid_engines={"H2O": IAPWSWrapper})
            self.nw.solve('design')
            self.trap =True

        self.ean = ExergyAnalysis(self.nw, 
                        E_P=[ turbine_bus, product_bus], 
                        E_F=[fuel_bus, pump_bus, makeup_bus, ],
                        E_L=[pipe_fugitive_emission, blowdown_bus ]
                        )
        #ean.analyse(pamb=1, Tamb=20, Chem_Ex= get_chem_ex_lib("Ahrendts"))
        
        self.result()
        self.converged=True
        self.initialized = True
        self.old_nw = copy.deepcopy(self.nw)

    def recalculate_steam_net(self):
        self.calc_mains()
        if not self.converged:
            self.nw = self.old_nw
        
        self.converged = False
        try:
            self.nw.solve('design')
        except:
            return np.nan 
        self.result()
        self.calculate_impact()
        self.converged=True
        self.old_nw = self.nw

    def result(self):

        c_leak = self.nw.conns.loc["steam leak:out2_steam losses:in1"]['object']
        c02 = self.nw.conns.loc["steam leak:out1_controlvalve:in1"]['object']
        c03 = self.nw.conns.loc["back pressure turbine:out1_steam pipe:in1"]['object']
        cond_5 = self.nw.conns.loc["Injection:out1_heat sink:in1"]['object']
        cond_1 = self.nw.conns.loc["heat sink:out1_split condensate:in1"]['object']
        c01 = self.nw.conns.loc["controlvalve:out1_Injection:in1"]['object']
        c1 = self.nw.conns.loc["split condensate:out1_condensate pipe:in1"]['object']
        muw= self.nw.conns.loc["Make-up water:out1_Makeup water feed:in2"]['object']
        muw2=self.nw.conns.loc["leak makeup:out1_Makeup water feed:in3"]['object']
        
        boiler=self.nw.comps.loc["steam boiler"]['object']
        heat_sink=self.nw.comps.loc["heat sink"]['object']

        turbine_bus = self.nw.busses['turbines']

        leakage_loss= c_leak.m.val *(c_leak.h.val - muw2.h.val)
        pipe_loss = c02.m.val *c03.h.val - c02.m.val * c02.h.val #only steam pipe
        self.elec_factor= abs(turbine_bus.P.val/heat_sink.Q.val)  # *0.9 efficiency of generator
        self.boiler_factor = abs(boiler.Q.val/heat_sink.Q.val)
        self.losses=(pipe_loss+leakage_loss)/abs(heat_sink.Q.val)*1000 #boiler.Q.val+heat_sink.Q.val+bpt.P.val # 
        self.watertreatment_factor = abs(muw.m.val/heat_sink.Q.val)
        #calc exergy reduction:
        
        self.E_bpt= -turbine_bus.P.val#((c04.h.val*1000 -c03.h.val*1000) - self.Tamb* (c03.s.val - c04.s.val) )* c03.m.val
        if self.cond_inj:
            self.E_hs= ((cond_5.h.val*1000 -cond_1.h.val*1000) - (self.Tamb+273)* (cond_5.s.val - cond_1.s.val))* cond_5.m.val
        else:
            self.E_hs= ((c01.h.val*1000 -c1.h.val*1000) - (self.Tamb+273)* (c01.s.val - c1.s.val))* c01.m.val
        
        self.alloc_ex = self.E_hs /(self.E_hs + self.E_bpt)

    def calc_pressure(self):
        self.needed_pressure= PropsSI('P','Q',0,'T',self.needed_temperature+273,'IF97::water')*1E-5
        needed_enthalpy= PropsSI('H','Q',0,'T',self.needed_temperature+273,'IF97::water')
        

    def export_bw_dataset(self, database=None, dataset_correction=1):
        if not self.converged:
            raise Exception("Steam net is not calculated yet.") 
        
        self.dataset_correction=dataset_correction

        if self.bw_heat == None or self.bw_electricity ==None:
            raise Exception("brightway25 datasets for steam and/or electricity production are not defined.") 
        
        if database== None:
            database = f"utility LCA db" 
        if database not in bd.databases:
            bd.Database(database).register() 
        now= datetime.datetime.now()
        code= f'steam_{self.needed_temperature}_°C_{now}'
        steam_node = bd.Database(database).new_node(
            name= 'Process heat from steam network',
            unit= 'MJ',
            temperature =self.needed_temperature,
            code= code
        )
        steam_node.save()
        print(code)
        
        if self.allocate == 'credit':
            steam_node.new_exchange(
                input=self.bw_heat,
                amount=  self.boiler_factor*self.dataset_correction,
                type = 'technosphere',
            ).save()
            #substitution of electricity:
            steam_node.new_exchange(
                input=self.bw_electricity,
                amount= - self.elec_factor/3.6, #kwh
                type = 'technosphere',
            ).save()
            if self.bw_water_treatment != None:
                steam_node.new_exchange(
                    output=self.bw_water_treatment,
                    amount= self.watertreatment_factor, #
                    type = 'technosphere',
                ).save()
        elif self.allocate == 'by exergy':
            
            steam_node.new_exchange(
                input=self.bw_heat,
                amount=  self.boiler_factor  * self.alloc_ex*self.dataset_correction, 
                type = 'technosphere', 
            ).save()
            code_elec= f'electricity_from_steam_net_{self.needed_temperature}_°C_{now}'
            electricity_node = bd.Database(database).new_node(
                name= 'Electricity from steam network',
                unit= 'kWh',
                code= code_elec
            )
            electricity_node.save()
            print(code_elec)
            electricity_node.new_exchange(
                input=self.bw_heat,
                amount=  self.boiler_factor  * (1-self.alloc_ex) /3.6 *self.dataset_correction, 
                type = 'technosphere', 
            ).save()
            electricity_node.new_exchange(
                input=electricity_node,
                amount=  1, 
                type = 'production', 
            ).save()
            if self.bw_water_treatment != None:
                steam_node.new_exchange(
                    output=self.bw_water_treatment,
                    amount= self.watertreatment_factor * self.alloc_ex, #
                    type = 'technosphere',
                ).save()
                electricity_node.new_exchange(
                    output=self.bw_water_treatment,
                    amount= self.watertreatment_factor * (1-self.alloc_ex)/3.6, #
                    type = 'technosphere',
                ).save()

        steam_node.new_exchange(
            input=steam_node,
            amount= 1,
            type = 'production',
        ).save()
        
        return code
    def calc_mains(self):
        
        self.mains.sort()
        self.calc_pressure()
        s_superheating_max_pressure=  PropsSI('S','P',self.mains[0]*1E5,'Q',1,'IF97::water') 
        self.h_superheating_max_pressure=  PropsSI('H','P',self.max_pressure*1E5,'S',s_superheating_max_pressure,'IF97::water') *1E-3
        if self.needed_pressure*1.05 > self.mains[-1]:
            print('needed pressure larger than net pressure!')
        self.main_pressure = min((x for x in self.mains if x >= self.needed_pressure*1.01), default=None) 
        #print(f'self.main_pressure: {self.main_pressure}', f'self.needed_pressure: {self.needed_pressure}')
        

    def generate_steam_net(self, needed_temperature,heat= 1000E3,  allocate='credit'):
        self.needed_temperature =needed_temperature
        self.allocate = allocate
        self.heat=heat

        self.calc_mains()
        
        i=0
        while i < 10:

            self.calc_steam_net()
            if self.nw.converged:
                break
            i+=1
        else:
            raise Exception('Steam net calculation failed. Please give it another try!')
        return self.calculate_impact(allocate)

    def calculate_background(self, allocate= 'credit'):
        #calculate steam impact:
        if isinstance(self.impact_category , list)and isinstance(self.bw_heat, bd.backends.proxies.Activity)and isinstance(self.bw_electricity, bd.backends.proxies.Activity) :
            method_config= {'impact_categories':self.impact_category}
            
            functional_units = {"process heat": {self.bw_heat.id: 1},
                                "electricity": {self.bw_electricity.id: 1}}
            data_objs_steam = bd.get_multilca_data_objs(functional_units, method_config)
            self.net_lca = bc.MultiLCA(demands=functional_units,
                       method_config=method_config, 
                       data_objs=data_objs_steam
                       )
            self.net_lca.lci()
            self.net_lca.lcia()
        return self.calculate_impact(allocate)

    def calculate_impact(self, allocate = 'credit'):    
        self.impact ={}
        
        if  isinstance(self.net_lca , bc.multi_lca.MultiLCA):
            for cat in self.impact_category:
                
                if allocate == 'credit':
                    self.impact[cat]= self.net_lca.scores[(cat, 'process heat')]* self.boiler_factor - self.net_lca.scores[(cat, 'electricity')]*self.elec_factor /3.6 #if impact/kWh
                elif allocate == 'by exergy':
                    self.impact[cat]= self.net_lca.scores[(cat, 'process heat')]* self.boiler_factor * self.alloc_ex

            
        else: #self.impact_category == None or : #no bw dataset. use impact_heat/impact_elec factors for category climate change:
            if allocate == 'credit':
                self.impact= self.impact_heat* self.boiler_factor - self.impact_elec*self.elec_factor
            elif allocate == 'by exergy':
                self.impact= self.impact_heat* self.boiler_factor * self.alloc_ex

        return self.impact
        

    def plot_hs(self):
        # Initial Setup
        diagram = FluidPropertyDiagram('water')
        diagram.set_unit_system(T='°C', p='bar', h='kJ/kg')

        # Storing the model result in the dictionary
        result_dict = {}
        result_dict.update(
            {cp.label: cp.get_plotting_data()[1] for cp in self.nw.comps['object']
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
    
    def foreground_sensitivity_study(self, 
                        makeup_factor,
                        Tamb,
                        leakage_factor,
                        pipe_length,
                        insulation_thickness,
                        wind_velocity,
                        needed_temperature,
                        ):
        self.makeup_factor=makeup_factor
        self.Tamb=Tamb
        self.leakage_factor=leakage_factor
        self.pipe_length=pipe_length
        self.insulation_thickness=insulation_thickness
        self.wind_velocity=wind_velocity
        self.needed_temperature=needed_temperature
        #i=1
        
        
        if  self.initialized and self.converged:
            try:
                self.calc_mains()
                self.change_parameters()
                self.recalculate_steam_net()
            except:
                print('didnt worked')
                return np.nan 
        else:
            try:
                self.generate_steam_net(needed_temperature, allocate='credit')
            except:
                return np.nan 
                
        if isinstance(self.impact, dict):
            return list(self.impact.values())[0] 
        else: 
            return self.impact 
        #self.export_bw_dataset

    def change_parameters(self):
        # makeup_factor:
        muw= self.nw.conns.loc["Make-up water:out1_Makeup water feed:in2"]['object']
        c04= self.nw.conns.loc["steam boiler:out1_back pressure turbine:in1"]['object']
        muw.set_attr(m=Ref(c04, self.makeup_factor, 0))

        #Tamb:
        self.nw.comps.loc['steam pipe']['object'].set_attr(Tamb = self.Tamb, 
                                                        L = self.pipe_length,
                                                        insulation_thickness= self.insulation_thickness,
                                                        wind_velocity=self.wind_velocity)
        self.nw.comps.loc['condensate pipe']['object'].set_attr(Tamb = self.Tamb, 
                                                        L = self.pipe_length,
                                                        insulation_thickness = self.insulation_thickness,
                                                        wind_velocity=self.wind_velocity)
        
        
        #muw.set_attr(T= self.Tamb)
        #muw2
        self.nw.conns.loc["leak makeup:out1_Makeup water feed:in3"]['object'].set_attr(T=self.Tamb)

        #leakage_factor:
        c022= self.nw.conns.loc["steam pipe:out1_steam leak:in1"]['object']
        self.nw.conns.loc["steam leak:out2_steam losses:in1"]['object'].set_attr(m=Ref(c022, self.leakage_factor, 0))

        #needed pressure:
        self.nw.conns.loc["controlvalve:out1_Injection:in1"]['object'].set_attr(p = self.needed_pressure)
