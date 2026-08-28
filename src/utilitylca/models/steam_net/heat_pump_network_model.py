import numpy as np
import tespy
from tespy.components import (
    Source, Sink, Pump, 
    Pipe, CycleCloser, SimpleHeatExchanger, Valve, Merge, 
    Splitter, 
    DropletSeparator,
    PowerSink, PowerSource, Generator,  PowerBus
)

from tespy.connections import Connection, Ref, PowerConnection
from CoolProp.CoolProp import PropsSI

import logging

logger = logging.getLogger(__name__)


def create_heat_pump_model(steam_lca):

    
    logging.basicConfig(filename='logs.log', 
                        filemode="w",
                        level=logging.INFO)
    steam_lca.cond_inj = False
    steam_lca.trap=False
    steam_lca.converged =False

    steam_lca.model.set_attr(iterinfo=True)
    steam_lca.model.units.set_defaults(temperature='degC', pressure='bar', enthalpy='kJ / kg')


    # create steam components
    if True:
    
        #boiler = SimpleHeatExchanger('steam boiler' , dissipative=False)
        #bpt = Turbine('back pressure turbine')
        pipe_warm =  Pipe('steam pipe', dissipative=True)
        
        valve = Valve('controlvalve')
        hex_heat_sink = SimpleHeatExchanger('hex heat sink', dissipative=False)
        pipe_cold= Pipe('condensate pipe',dissipative=True)
        feed_pump= Pump('feedpump')
        condensate_pump= Pump('condensate pump')
        #cycl=CycleCloser('CycleCloser')
        
        steam_losses = Sink('steam losses')
        steam_leak= Splitter("steam leak")
        makeup_leak =Source('leak makeup')
        
        makeup=Source("Make-up water")
        blowdown= Sink("blowdown wastewater")
        cond_waste= Sink("pipe condensate wastewater")
        merge = Merge("Makeup water feed", num_in=3)
        
        split= Splitter("remove wastewater")
        diversion= Splitter("divert steam from network")
        conflation= Merge("conflation condensate to network")
        network_heat_sink = SimpleHeatExchanger('network condensation', dissipative=False)
        valve_cond_nw = Valve('relax_cond_network')
        valve_cond = Valve('relax_cond')

        valve_after_main_process = tespy.components.Valve('valve_after_main_process')
        valve_after_net_process = tespy.components.Valve('valve_after_net_process')

    # create heat pump components
    if True:
        cycle_closer = tespy.components.CycleCloser('cycle closer')  # nur für die berechnung des Kreislaufs notwendig
        compressor_hp = tespy.components.Compressor('compressor_1')   # kompressor im geschlossenen hthp kreislauf
        expansion_valve = tespy.components.Valve('expansion valve')  # expansionsventil im geschlossenen hthp kreislauf
        heat_exchanger_at_source = tespy.components.HeatExchanger('heat exchanger at source')   # verdapfer: wärmeübertrager an der quellenseite 
        heat_exchanger_at_sink = tespy.components.HeatExchanger('heat exchanger at sink')       # kondensator: wärmeübertrager an der senkenseite
        heat_source_in = tespy.components.Source('heat source in')   # wärmequelle eintritt
        heat_source_out = tespy.components.Sink('heat source out')   # wärmequelle austritt
        compressor_mvr = tespy.components.Compressor('mvr compressor')   # mvr kompressor
        #steam_main = tespy.components.Sink('steam main')  # dampfnetz anschluss


    # create temporary components
    if True:
        # condensate water sink
        condensate_sink = tespy.components.Sink('condensate water sink')


        # feed water
        feed_water = tespy.components.Source('feedwater source')     # später: speisewasserpumpe (aus dampfnetz?)
        

    # create heat pump connections
    if True:
        c_cycle_closer_to_compressor = Connection(cycle_closer, 'out1', compressor_hp, 'in1', label='hp_01')
        c_compressor_to_heat_exchanger_sink = Connection(compressor_hp, 'out1', heat_exchanger_at_sink, 'in1', label='hp_02')
        c_heat_exchanger_sink_to_expansion_valve = Connection(heat_exchanger_at_sink, 'out1', expansion_valve, 'in1', label='hp_03')
        c_expansion_valve_to_heat_exchanger_source = Connection(expansion_valve, 'out1', heat_exchanger_at_source, 'in2', label='hp_04')
        c_heat_exchanger_source_to_cycle_closer = Connection(heat_exchanger_at_source, 'out2', cycle_closer, 'in1', label='hp_05')

        # heat source
        c_heat_exchanger_at_source_to_heat_source_in = Connection(heat_source_in, 'out1',heat_exchanger_at_source, 'in1')
        c_heat_exchanger_at_source_to_heat_source_out = Connection(heat_exchanger_at_source, 'out1', heat_source_out, 'in1')

        # mvr
        c_heat_exchanger_at_sink_to_mvr = Connection(heat_exchanger_at_sink,'out2',compressor_mvr,'in1')
        #c_mvr_to_steam_main = Connection(compressor_mvr,'out1',steam_main,'in1')

        # add components and connections to the network
        steam_lca.model.add_conns(c_cycle_closer_to_compressor,
                                c_compressor_to_heat_exchanger_sink,
                                c_heat_exchanger_sink_to_expansion_valve,
                                c_expansion_valve_to_heat_exchanger_source,
                                c_heat_exchanger_source_to_cycle_closer,
                                c_heat_exchanger_at_source_to_heat_source_in,
                                c_heat_exchanger_at_source_to_heat_source_out,
                                c_heat_exchanger_at_sink_to_mvr,
                                #c_mvr_to_steam_main
                                )    

    # create connections between heat pump and steam net
    #c0_6_steam_net_to_condensate_sink = Connection(feed_pump, 'out1', condensate_sink, 'in1')

    c0_5_merge_condensate_to_temporary_condensate_sink = Connection(merge, 'out1', condensate_sink, 'in1') #c4

    c_1_5_mvr_to_steam_main = Connection(compressor_mvr,'out1',pipe_warm,'in1')

    steam_lca.model.add_conns(c0_5_merge_condensate_to_temporary_condensate_sink, c_1_5_mvr_to_steam_main)

    c_feed_water_to_heat_exchanger_at_sink = Connection(feed_water,'out1',heat_exchanger_at_sink,'in2')
    steam_lca.model.add_conns( c_feed_water_to_heat_exchanger_at_sink)
    
    # connection attributes:
    # besser: berechnung über kondensationsentalpie
    def calc_starting_value_mass_flow(steam_lca):
        h_liquid = PropsSI('H','P',steam_lca.main_pressure*1E5,'Q',0,'IF97::water')
        h_vapor = PropsSI('H','P',steam_lca.main_pressure*1E5,'Q',1,'IF97::water')
        delta_h = h_vapor - h_liquid
        m_dot = steam_lca.parameters['heat_capacity_pipe_network'].default / (delta_h)  # in kg/s
        return m_dot
    starting_value_mass_flow = calc_starting_value_mass_flow(steam_lca)

    #print(f'starting mass flow for steam net: {starting_value_mass_flow} kg/s')


    c_1_5_mvr_to_steam_main.set_attr(p=steam_lca.main_pressure,m0=starting_value_mass_flow)

    #c0_6_steam_net_to_condensate_sink.set_attr(p=steam_lca.parameters['max_pressure']) # temporär



    steam_overheat_before_mvr = steam_lca.parameters['steam_overheat_before_mvr'].default  # in degC   --> siedetemperatur = vorlauftemperatur - überhitzung
    feed_water_pressure = PropsSI('P',
                                  'T',steam_lca.parameters['vorlauftemperatur(condenser_outlet)'].default
                                  -steam_overheat_before_mvr + 273.15,
                                  'Q',0,'IF97::Water') / 1e5  # in bar
    #print(f"Feed water pressure: {feed_water_pressure} bar")
    
    c_feed_water_to_heat_exchanger_at_sink.set_attr(T=steam_lca.parameters['feed_water_temperature'].default,
                                                    fluid = {'water':1},
                                                    p=feed_water_pressure)
    
    # sättigungsdruck in der wärmesenke der wärmepumpe
    c0_5_merge_condensate_to_temporary_condensate_sink.set_attr(p=feed_water_pressure)
    

    #create steam connections:
    if True:

        # Änderungen
        #c0_6 = Connection(feed_pump, 'out1', cycl, 'in1', label='c0_6') #c5
        #c0_7 = Connection(cycl, 'out1', boiler, 'in1', label='c0_7') #c05
        #c1_6 = Connection(boiler, 'out1', bpt, 'in1', label='c1_6') #c04
        #c1_5 = Connection(bpt, 'out1', pipe_warm, 'in1', label='c1_5') #c03

        # pumpe nach prozess durch drossel erstezen
        # das wird bei desuperheat_steam = True wahrscheinlich probleme machen
        #c0_1 = Connection(hex_heat_sink, 'out1', condensate_pump, 'in1', label='c0_1') #c1
        #c0_11 = Connection(condensate_pump, 'out1', conflation, 'in2', label='c0_11') #c1
        c0_1_hex_heat_sink_to_valve_cold1 = Connection(hex_heat_sink, 'out1', valve_after_main_process, 'in1', label='c0_1_hex_heat_sink_to_valve_cold1') #c1
        c0_11_valve_after_main_process_to_conflation = Connection(
            valve_after_main_process, 'out1', conflation, 'in2', 
            label='c0_11_valve_after_main_process_to_conflation') #c1


        #drossel nach netzprozess einfügen. hier waren doch keine änderungen nötig, abbildung falch.
        cnw2= Connection(network_heat_sink, 'out1', valve_cond_nw, 'in1',label='cnw2')
        cnw3= Connection(valve_cond_nw, 'out1', conflation, 'in1',label='cnw3')

        # feedwater pumpe raus genommen. erstmal direkt in die tempräre senke
        #c0_5 = Connection(merge, 'out1', feed_pump, 'in1', label='c0_5') #c4
        

        ## Gleich geblieben
        c1_4= Connection(pipe_warm, 'out1', steam_leak, 'in1', label='c1_4') #c022
        c1_3 = Connection(steam_leak, 'out1', diversion, 'in1',label='c1_3') #c023

        cnw1= Connection(diversion, 'out1', network_heat_sink, 'in1',label='cnw1')
        

        c_leak = Connection(steam_leak, 'out2', steam_losses, 'in1', label='c_leak')
        muw2 = Connection(makeup_leak, 'out1', merge, 'in3', label='muw2')

        c1_2 = Connection(diversion, 'out2', valve, 'in1',label='c1_2') #c02
        c1_1= Connection(valve, 'out1', hex_heat_sink, 'in1', label='c1_1') #c01
        
        
        c0_2 = Connection(conflation, 'out1', pipe_cold, 'in1', label='c0_2') #c11

        c0_3 = Connection(pipe_cold, 'out1', split, 'in1', label='c0_3') #c2
        c0_4 = Connection(split, 'out1', merge, 'in1', label='c0_4') #c3
        
        

        muw = Connection(makeup, 'out1', merge, 'in2', label='muw')
        wawa = Connection(split, 'out2', blowdown, 'in1', 'c_blowdown')

        steam_lca.model.add_conns(#c1_6,
                                #c1_5,
                                c1_4, c1_3, c1_2, c1_1, 
                                cnw1, cnw2,cnw3,
                                c_leak,
                                #c0_11,
                                c0_11_valve_after_main_process_to_conflation,
                                c0_1_hex_heat_sink_to_valve_cold1,
                                #c0_1,
                                c0_2, c0_3, c0_4, 
                                #c0_5,
                                #c_06,
                                #c0_7,
                                muw, wawa, muw2)
        
    #set steam attributes:
    if True:
        #boiler.set_attr(pr = 1, power_connector_location="inlet")
        #c1_6.set_attr(fluid={"H2O": 1}, h= steam_lca.h_superheating_max_pressure)
        #c0_7.set_attr(p0=steam_lca.main_pressure,)
        #bpt.set_attr(eta_s = 0.85, )
        #c1_5.set_attr(p=steam_lca.main_pressure, h0=steam_lca.h_superheating_max_pressure)

        pipe_warm.set_attr(pr=0.95, 
            Tamb = steam_lca.parameters['Tamb'].default, 
            L=steam_lca.parameters['pipe_length'].default, 
            D='var', ks=4.57e-5,
            power_connector_location="outlet",
            insulation_thickness=steam_lca.parameters['insulation_thickness'].default ,
            insulation_tc= 0.035, pipe_thickness=0.004,material='Steel', 
            wind_velocity=steam_lca.parameters['wind_velocity'].default, 
            environment_media = steam_lca.parameters['environment_media'].default
                ) 
        c_leak.set_attr(m=Ref(c1_4, steam_lca.parameters['leakage_factor'].default, 0))
        c1_1.set_attr(p = steam_lca.needed_pressure,
                    #h0=steam_lca.h_superheating_max_pressure,
                    )
        hex_heat_sink.set_attr(pr=1,
                            Q=-steam_lca.parameters['heat'].default, 
                            power_connector_location="outlet")
        
        mains_sorted = sorted(steam_lca.parameters['mains'].default)
        if steam_lca.main_pressure in mains_sorted:
            idx = mains_sorted.index(steam_lca.main_pressure)
            next_main = mains_sorted[idx - 1] if idx - 1 >= 0 else 1.013
        else:
            raise ValueError("Main pressure not found in mains list")
        

        # robin
        #c0_2.set_attr(p=steam_lca.main_pressure )
        #c0_1.set_attr(x=0)          

        pipe_cold.set_attr(pr=0.95, 
            Tamb = steam_lca.parameters['Tamb'].default,
            L=steam_lca.parameters['pipe_length'].default, D='var',  ks=4.57e-5,
            power_connector_location="outlet",
            insulation_thickness=steam_lca.parameters['insulation_thickness'].default ,
            insulation_tc= 0.035, 
            pipe_thickness=0.004,material='Steel', 
            wind_velocity= steam_lca.parameters['wind_velocity'].default, 
            environment_media = steam_lca.parameters['environment_media'].default
                )

        #c0_5.set_attr(p0=steam_lca.needed_pressure,)
        
        #c0_6.set_attr(p=steam_lca.parameters['max_pressure'], h0=steam_lca.h_superheating_max_pressure,)

        muw.set_attr(m=Ref(c_1_5_mvr_to_steam_main, steam_lca.parameters['makeup_factor'].default, 0),              # was c1_6 before
                        T=steam_lca.parameters['Tamb'].default,
                        fluid={"H2O": 1},  
                        p0=1.013)
        muw2.set_attr(m=Ref(c_leak, 1, 0), 
                        T=steam_lca.parameters['Tamb'].default,
                        fluid={"H2O": 1}, 
                        p0=1.013)
        
        wawa.set_attr(m=Ref(c_1_5_mvr_to_steam_main, steam_lca.parameters['makeup_factor'].default, 0))          # was c1_6 before
        #feed_pump.set_attr(eta_s =0.95)
        condensate_pump.set_attr(eta_s=0.95)
        network_heat_sink.set_attr(pr=1, 
                                Q=-(steam_lca.parameters['heat_capacity_pipe_network'].default-steam_lca.parameters['heat'].default),
                                power_connector_location="outlet",
                                )
        cnw2.set_attr(x=0)                                      # vollständige kondensation im net prozess. vor der drosselung auf psatHP
        c0_1_hex_heat_sink_to_valve_cold1.set_attr(x=0)         # vollständige kondensation im haupt prozess. vor der drosselung auf psatHP
    
    # set heat pump attributes:
    if True:
        # calculate missing parameters
        # Annahme: quelle kalte seite ist siedetemperatur, quelle warme seite etwas höher
        dt_source = 5
        dt_sink = 5
        T_working_fluid_after_heat_source = steam_lca.parameters['source_temperature_after_evaporator'].default - dt_source  # in degC  working fluid ist immer noch kälter als die quelle
        T_working_fluid_after_heat_sink = steam_lca.parameters['vorlauftemperatur(condenser_outlet)'].default + dt_sink # in degC  woking fluid ist immer noch wärmer als die senke
        
        
        p_sat_working_fluid_after_heat_source = PropsSI(
            'P',
            'T',T_working_fluid_after_heat_source + 273.15,
            'Q',1, str(steam_lca.parameters['working_fluid_coolprop_name'].default)) / 1e5  # in bar
        #Annahme: senke kalte seite ist kondensationstemperatur, senke warme seite etwas höher
        p_sat_working_fluid_after_heat_sink = PropsSI(
            'P','T',T_working_fluid_after_heat_sink + 273.15,
            'Q',0, str(steam_lca.parameters['working_fluid_coolprop_name'].default)) / 1e5  # in bar
        


        # components
        compressor_hp.set_attr(eta_s = 1)                   #  = 1 resultiert nicht in gütegrad 1 
        heat_exchanger_at_sink.set_attr(pr1 = 1,pr2 = 1)             # annahme: kein druckverlust im wärmeübertrager
        heat_exchanger_at_source.set_attr(pr1 = 1,pr2= 1)           # annahme: kein druckverlust im wärmeübertrager



        compressor_mvr.set_attr(eta_s = steam_lca.parameters['mvr_compressor_isentropic_efficiency'].default)
        # connections
        c_cycle_closer_to_compressor.set_attr(fluid ={ steam_lca.parameters['working_fluid'].default:1},
                                            x=1,
                                            p=p_sat_working_fluid_after_heat_source,
                                            m0=steam_lca.parameters['heat_capacity_pipe_network'].default/1E6)    # x=1 flüssigkeit im verdichter wäre problematisch  # hier lieber p=psat(T) als T vorgeben

        c_heat_exchanger_sink_to_expansion_valve.set_attr(x=0,p=p_sat_working_fluid_after_heat_sink) # x=0 vollständige kondensation standart besser leicht unterkühlen?
                                    
        c_heat_exchanger_at_source_to_heat_source_in.set_attr(
            T = steam_lca.parameters['source_temperature_before_evaporator'].default,
            fluid = {steam_lca.parameters['heat_source_fluid'].default:1})
        
        c_heat_exchanger_at_source_to_heat_source_out.set_attr(
            T=steam_lca.parameters['source_temperature_after_evaporator'].default,p=1)  # ausstritt mit atmosphärendruck



        

        # mvr 

        c_heat_exchanger_at_sink_to_mvr.set_attr(T = steam_lca.parameters['vorlauftemperatur(condenser_outlet)'].default) ## ist wärmer als psat

        #c_mvr_to_steam_main.set_attr(p = steam_lca.needed_pressure)  # anschluss an dampfnetz mit definiertem drucklevel        
    

    # create power connections:
    if True:
       
        pipe_diss_sink =PowerSink('pipe dissipative losses sink')
        pipe_diss_bus = PowerBus('pipe dissipative losses bus', num_in =2, num_out=1)

        e_pi_h = PowerConnection(pipe_warm, 'heat', pipe_diss_bus, 'power_in1')
        e_pi_c = PowerConnection(pipe_cold, 'heat', pipe_diss_bus, 'power_in2')
        e_pi_sink = PowerConnection(pipe_diss_bus, 'power_out1', pipe_diss_sink, 'power', label='e_pi_sink')
        
        heat_sink =PowerSink('heat sink')
        e_heat_sink =PowerConnection( hex_heat_sink,'heat',heat_sink, 'power', label='e_heat_sink')

        nw_heat_sink =PowerSink('nw heat sink')
        e_nw_heat_sink =PowerConnection( network_heat_sink,'heat',nw_heat_sink, 'power', label='e_nw_heat_sink')

        #pump_psource = PowerSource('feedpump powersource')
        #e_pump = PowerConnection(pump_psource, 'power', feed_pump, 'power', label='e_pump')

        mvr_source = PowerSource('MVR power source')
        e_mvr = PowerConnection(mvr_source, 'power', compressor_mvr, 'power', label= 'e_mvr' )

        hp_source = PowerSource('HP power source')
        e_hp = PowerConnection(hp_source, 'power', compressor_hp, 'power', label= 'e_hp' )

        steam_lca.model.add_conns(
                            e_pi_c, e_pi_h, e_pi_sink,
                            e_heat_sink, e_nw_heat_sink,
                            #e_pump, 
                            e_mvr, e_hp
        )
        #2. Run: 

    logger.info('Start first solve')
    steam_lca.model.solve('design')
    muw.set_attr(T=None)
    muw.set_attr(T=Ref(c0_3, 1, 0))
    logger.info('Start second solve')
    steam_lca.model.solve('design')

    #3. Run: implement condensate injection:
   # if superheated inject condensate:
    if c1_4.x.val in [-1,1] and steam_lca.desuperheat_steam:
        steam_lca.model.del_conns(c1_1, c0_1)
        merge_injection = Merge("Injection")
        dummy_sink2= Sink('dummy sink2')
        injection_source =Source('injection_source')
        condensate_split= Splitter("split condensate")
        
        c1_1= Connection(valve, 'out1', merge_injection, 'in1', label='c1_1')
        cond_3 = Connection(injection_source, 'out1', merge_injection, 'in2')
        cond_5 = Connection(merge_injection, 'out1', hex_heat_sink, 'in1', label= 'cond_5')

        cond_1 = Connection(hex_heat_sink, 'out1', condensate_split, 'in1', label='cond_1')
        cond_2 = Connection(condensate_split, 'out2', dummy_sink2, 'in1')
        c0_1 = Connection(condensate_split, 'out1', valve_cond, 'in1', label='c0_1')
        steam_lca.model.add_conns(cond_1, cond_2, cond_3,cond_5,c1_1,c0_1)

        c1_1.set_attr(p = steam_lca.needed_pressure)
        cond_1.set_attr(x=0)

        c0_1.set_attr(m=Ref(c1_1,1,0))


        cond_3.set_attr(x=0, 
                        fluid={"H2O": 1}, 
                        )
        cond_5.set_attr(x=1)
        logger.info('Start third solve')
        steam_lca.model.solve('design')
        steam_lca.cond_inj =True
    # when steam is not saturated trap condensate (experimental): 
    elif 0< c1_4.x.val <1:
        merge.set_attr(num_in=4)
        steam_lca.model.del_conns(c1_2)
        makeup_trap =Source('trap makeup')
        cond_trap= DropletSeparator('condensate trap') 

        muw3 = Connection(makeup_trap, 'out1', merge, 'in4', label='muw3')
        c023= Connection(steam_leak, 'out1', cond_trap, 'in1')
        c024= Connection(cond_trap, 'out2', valve, 'in1')
        c_trap_waste = Connection(cond_trap, 'out1', cond_waste, 'in1', 'c_trap_waste ')
        
        steam_lca.model.add_conns(c023, c024, c_trap_waste, muw3)

        muw3.set_attr(m=Ref(c_trap_waste, 1, 0), T=steam_lca.parameters['Tamb'].default,
                      fluid={"H2O": 1}, 
                      )
        logger.info('Start third solve')
        steam_lca.model.solve('design')
        steam_lca.trap =True
    
    if True:
        def calculate_lorenz_COP_and_delta_T_lorenz():

            # die wärmesenke hat keinen exponentiellen abfall, da das wasser erhitzt wird und verdampft. lorenz hier also eigentlich nicht anwendbar. carnot aber auch nicht

            # log mean senke aus wasser T vor wärmesenke und T nach wärmesenke
            T1_sink = c_feed_water_to_heat_exchanger_at_sink.T.val + 273.15  # K
            T2_sink = c_heat_exchanger_at_sink_to_mvr.T.val + 273.15  # K
            T_lm_sink = (T2_sink - T1_sink) / np.log(T2_sink / T1_sink)

            # log mean quelle aus wasser T vor wärmepumpe und T nach wärmepumpe
            T1_source = c_heat_exchanger_at_source_to_heat_source_in.T.val + 273.15  # K
            T2_source = c_heat_exchanger_at_source_to_heat_source_out.T.val + 273.15  # K
            T_lm_source = (T2_source - T1_source) / np.log(T2_source / T1_source)


            lorenz_COP = T_lm_sink / (T_lm_sink - T_lm_source)
            deltaT = T_lm_sink - T_lm_source
            return lorenz_COP, deltaT
        def calculate_carnot_COP_carnot_dt():
            # t hot = siedetemperatur wasser am kondensator
            T_hot = c_heat_exchanger_at_sink_to_mvr.T.val + 273.15 - steam_lca.params['steam_overheat_before_mvr']  # K
            # tcold = wärmequelle eingangstemperatur wasser
            T_cold = c_heat_exchanger_at_source_to_heat_source_in.T.val + 273.15  # K
            carnot_COP = T_hot / (T_hot - T_cold)
            return carnot_COP, T_hot - T_cold



        lorenz_COP, deltaT_lorenz = calculate_lorenz_COP_and_delta_T_lorenz()
        carnot_COP, carnot_dt = calculate_carnot_COP_carnot_dt()

        # leere zeile
        print("")
        # alle temperaturen des arbeitsfluids ausgeben
        print("Heat pump working fluid temperatures:")
        print(f"Compressor inlet temperature (parameter): {c_cycle_closer_to_compressor.T.val} °C")
        print(f"Compressor outlet temperature(result): {c_compressor_to_heat_exchanger_sink.T.val} °C")


        # print all results sorted by connection. pressure, temperature, mass flow
        print("heat pump results:")
        print(f"cold water mass flow: {c_heat_exchanger_at_source_to_heat_source_in.m.val} kg/s")
        print(f"source inlet temperature: {c_heat_exchanger_at_source_to_heat_source_in.T.val} °C")
        print(f"source outlet temperature: {c_heat_exchanger_at_source_to_heat_source_out.T.val} °C")
        print(f"heat pump working fluid mass flow: {c_cycle_closer_to_compressor.m.val} kg/s")
        print(f"heat delivered to heat sink: {heat_exchanger_at_sink.Q.val} W")
        print(f"compressor power input: {compressor_hp.P.val} W")
        print(f"heat taken from heat source: {heat_exchanger_at_source.Q.val} W")
        print("")
        print(f"heat pump COP: {abs(heat_exchanger_at_sink.Q.val / compressor_hp.P.val)}")  # COP = Q_h / W_compressor
        print(f"lorenz delta T: {deltaT_lorenz}")
        print(f"lorenz COP: {lorenz_COP}")
        print(f"lorenz Gütegrad der Wärmepumpe: {abs((heat_exchanger_at_sink.Q.val / compressor_hp.P.val) / lorenz_COP)}")
        print(f"carnot delta T: {carnot_dt}")
        print(f"carnot COP: {carnot_COP}")
        print(f"carnot Gütegrad der Wärmepumpe: {abs((heat_exchanger_at_sink.Q.val / compressor_hp.P.val) / carnot_COP)}")
        # print mvr power demand and mvr output steam properties
        print("")
        print(f"MVR compressor power input: {compressor_mvr.P.val} W")
        print(f"MVR steam mass flow: {c_heat_exchanger_at_sink_to_mvr.m.val} kg/s")


        # print steam pressure before mvr
        p_steam_before_mvr = c_heat_exchanger_at_sink_to_mvr.p.val  # in bar
        print(f"Steam pressure before MVR: {p_steam_before_mvr:.2f} bar")

        # print superheat of steam after mvr
        t_steam_after_mvr = c_1_5_mvr_to_steam_main.T.val + 273.15  # in K
        p_steam_after_mvr = c_1_5_mvr_to_steam_main.p.val * 1e5  # in Pa
        T_sat_steam_after_mvr = PropsSI('T', 'P', p_steam_after_mvr, 'Q', 1,'IF97::Water')  # K
        superheat_steam_after_mvr = t_steam_after_mvr - T_sat_steam_after_mvr  # K == °C
        print(f"Superheat of steam after MVR: {superheat_steam_after_mvr:.2f} °C")

    # print steam net results
    if True:
        print("")
        print("Steam net results:")
        print(f"Needed pressure for heat sink: {steam_lca.needed_pressure} bar")
        # print pessure main
        print(f"Steam main pressure: {steam_lca.main_pressure} bar")
        # mass flow throug feedwater pump
        #print(f"Mass flow through feedwater pump: {c0_5.m.val} kg/s")
        # temperature after network heat sink
        print(f"Temperature after network heat sink: {cnw2.T.val} °C")
        # pressure after network heat sink
        print(f"Pressure after network heat sink: {cnw2.p.val} bar")
        # same for the other heat sink
        print(f"Temperature after hex heat sink: {c0_1_hex_heat_sink_to_valve_cold1.T.val} °C")
        print(f"Pressure after hex heat sink: {c0_1_hex_heat_sink_to_valve_cold1.p.val} bar")
    
        #entalpy before and after heat sinks
        print(f"Enthalpy before hex heat sink: {c1_1.h.val} kJ/kg")
        print(f"Enthalpy after hex heat sink: {c0_1_hex_heat_sink_to_valve_cold1.h.val} kJ/kg")
        print(f"Enthalpy before network heat sink: {cnw1.h.val} kJ/kg")
        print(f"Enthalpy after network heat sink: {cnw2.h.val} kJ/kg")
