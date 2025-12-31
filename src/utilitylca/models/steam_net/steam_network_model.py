from tespy.components import (
    Turbine, Source, Sink, Pump, 
    Pipe, CycleCloser, SimpleHeatExchanger, Valve, Merge, 
    Splitter, 
    DropletSeparator,
    PowerSink, PowerSource, Generator,  PowerBus
)

from tespy.connections import Connection, Ref, PowerConnection
import logging

logger = logging.getLogger(__name__)

def create_steam_net(steam_lca):
    
    logging.basicConfig(filename='logs.log', 
                        filemode="w",
                        level=logging.INFO)
    steam_lca.cond_inj = False
    steam_lca.trap=False
    steam_lca.converged =False

    steam_lca.model.set_attr(iterinfo=False)
    steam_lca.model.units.set_defaults(temperature='degC', pressure='bar', enthalpy='kJ / kg')
    # create components
    boiler = SimpleHeatExchanger('steam boiler' , dissipative=False)
    bpt = Turbine('back pressure turbine')
    pipe_warm =  Pipe('steam pipe', dissipative=True)
    
    valve = Valve('controlvalve')
    hex_heat_sink = SimpleHeatExchanger('hex heat sink', dissipative=False)
    pipe_cold= Pipe('condensate pipe',dissipative=True)
    feed_pump= Pump('feedpump')
    condensate_pump= Pump('condensate pump')
    cycl=CycleCloser('CycleCloser')
    
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

    #create connections:
    c0_7 = Connection(cycl, 'out1', boiler, 'in1', label='c0_7') #c05
    c1_6 = Connection(boiler, 'out1', bpt, 'in1', label='c1_6') #c04
    c1_5 = Connection(bpt, 'out1', pipe_warm, 'in1', label='c1_5') #c03
    c1_4= Connection(pipe_warm, 'out1', steam_leak, 'in1', label='c1_4') #c022
    c1_3 = Connection(steam_leak, 'out1', diversion, 'in1',label='c1_3') #c023

    cnw1= Connection(diversion, 'out1', network_heat_sink, 'in1',label='cnw1')
    cnw2= Connection(network_heat_sink, 'out1', valve_cond_nw, 'in1',label='cnw2')
    cnw3= Connection(valve_cond_nw, 'out1', conflation, 'in1',label='cnw3')

    c_leak = Connection(steam_leak, 'out2', steam_losses, 'in1', label='c_leak')
    muw2 = Connection(makeup_leak, 'out1', merge, 'in3', label='muw2')

    c1_2 = Connection(diversion, 'out2', valve, 'in1',label='c1_2') #c02
    c1_1= Connection(valve, 'out1', hex_heat_sink, 'in1', label='c1_1') #c01
    
    c0_1 = Connection(hex_heat_sink, 'out1', condensate_pump, 'in1', label='c0_1') #c1
    c0_11 = Connection(condensate_pump, 'out1', conflation, 'in2', label='c0_11') #c1
    c0_2 = Connection(conflation, 'out1', pipe_cold, 'in1', label='c0_2') #c11

    c0_3 = Connection(pipe_cold, 'out1', split, 'in1', label='c0_3') #c2
    c0_4 = Connection(split, 'out1', merge, 'in1', label='c0_4') #c3
    c0_5 = Connection(merge, 'out1', feed_pump, 'in1', label='c0_5') #c4
    c0_6 = Connection(feed_pump, 'out1', cycl, 'in1', label='c0_6') #c5

    muw = Connection(makeup, 'out1', merge, 'in2', label='muw')
    wawa = Connection(split, 'out2', blowdown, 'in1', 'c_blowdown')

    steam_lca.model.add_conns(c1_6, c1_5, c1_4, c1_3, c1_2, c1_1, 
                              cnw1, cnw2,cnw3,
                              c_leak,
                              c0_11,
                              c0_1, c0_2, c0_3, c0_4, c0_5, c0_6, c0_7,
                              muw, wawa, muw2)
    #set attributes:
    boiler.set_attr(pr = 1, power_connector_location="inlet")
    c1_6.set_attr(fluid={"H2O": 1}, 
                    h= steam_lca.h_superheating_max_pressure)
    c0_7.set_attr(p0=steam_lca.main_pressure,)
    bpt.set_attr(eta_s = 0.85, )
    c1_5.set_attr(p=steam_lca.main_pressure, 
                 h0=steam_lca.h_superheating_max_pressure, 
                 )
    pipe_warm.set_attr(pr=0.95, 
        Tamb = steam_lca.params['Tamb'], 
        L=steam_lca.params['pipe_length'], 
        D='var', ks=4.57e-5,
        power_connector_location="outlet",
        insulation_thickness=steam_lca.params['insulation_thickness'] ,
        insulation_tc= 0.035, pipe_thickness=0.004,material='Steel', 
        wind_velocity=steam_lca.params['wind_velocity'], 
        environment_media = steam_lca.params['environment_media']
            ) 
    c_leak.set_attr(m=Ref(c1_4, steam_lca.params['leakage_factor'], 0))
    c1_1.set_attr(p = steam_lca.needed_pressure,
                 h0=steam_lca.h_superheating_max_pressure,
                 )
    hex_heat_sink.set_attr(pr=1,
                           Q=-steam_lca.params['heat'], 
                           power_connector_location="outlet")
    
    mains_sorted = sorted(steam_lca.params['mains'])
    if steam_lca.main_pressure in mains_sorted:
        idx = mains_sorted.index(steam_lca.main_pressure)
        next_main = mains_sorted[idx - 1] if idx - 1 >= 0 else 1.013
    else:
        raise ValueError("Main pressure not found in mains list")
    
    c0_2.set_attr(p=steam_lca.main_pressure 
                )
    pipe_cold.set_attr(pr=0.95, 
        Tamb = steam_lca.params['Tamb'],
        L=steam_lca.params['pipe_length'], D='var',  ks=4.57e-5,
        power_connector_location="outlet",
        insulation_thickness=steam_lca.params['insulation_thickness'] ,
        insulation_tc= 0.035, 
        pipe_thickness=0.004,material='Steel', 
        wind_velocity= steam_lca.params['wind_velocity'], 
        environment_media = steam_lca.params['environment_media']
            )

    c0_5.set_attr(p0=steam_lca.needed_pressure,
                )
    
    c0_6.set_attr(p=steam_lca.params['max_pressure'], 
                h0=steam_lca.h_superheating_max_pressure,
                )

    muw.set_attr(m=Ref(c1_6, steam_lca.params['makeup_factor'], 0), 
                    T=steam_lca.params['Tamb'],
                    fluid={"H2O": 1},  
                    p0=1.013)
    muw2.set_attr(m=Ref(c_leak, 1, 0), 
                    T=steam_lca.params['Tamb'],
                    fluid={"H2O": 1}, 
                    p0=1.013)
    
    wawa.set_attr(m=Ref(c1_6, steam_lca.params['makeup_factor'], 0))
    feed_pump.set_attr(eta_s =0.95)
    condensate_pump.set_attr(eta_s=0.95)
    network_heat_sink.set_attr(pr=1, 
                               Q=-(steam_lca.params['heat_capacity_pipe_network']-steam_lca.params['heat']),
                               power_connector_location="outlet",
                               )
    cnw2.set_attr(x=0)
    c0_1.set_attr(x=0)
    
    # create power connections:
    
    fuel_bus = PowerSource('boiler powersource')
    e_boil = PowerConnection(fuel_bus, 'power', boiler, 'heat', label= 'e_boil')
    
    turbine_gen = Generator('turbines')
    turbine_gen.set_attr(eta= 0.9)
    turbine_grid = PowerSink('grid')
    e_turb = PowerConnection(bpt, 'power', turbine_gen, 'power_in', label='e_turb')
    e_turb_grid =PowerConnection(turbine_gen, 'power_out', turbine_grid, 'power', 
                                label='e_turb_grid')

    pipe_diss_sink =PowerSink('pipe dissipative losses sink')
    pipe_diss_bus = PowerBus('pipe dissipative losses bus', num_in =2, num_out=1)

    e_pi_h = PowerConnection(pipe_warm, 'heat', pipe_diss_bus, 'power_in1')
    e_pi_c = PowerConnection(pipe_cold, 'heat', pipe_diss_bus, 'power_in2')
    e_pi_sink = PowerConnection(pipe_diss_bus, 'power_out1', pipe_diss_sink, 'power', label='e_pi_sink')
    
    heat_sink =PowerSink('heat sink')
    e_heat_sink =PowerConnection( hex_heat_sink,'heat',heat_sink, 'power', label='e_heat_sink')

    nw_heat_sink =PowerSink('nw heat sink')
    e_nw_heat_sink =PowerConnection( network_heat_sink,'heat',nw_heat_sink, 'power', label='e_nw_heat_sink')

    pump_psource = PowerSource('feedpump powersource')
    e_pump = PowerConnection(pump_psource, 'power', feed_pump, 'power', label='e_pump')


    steam_lca.model.add_conns(e_boil,
        e_turb,e_turb_grid,
                           e_pi_c, e_pi_h, e_pi_sink,
                           e_heat_sink, e_nw_heat_sink,
                           e_pump
    )
    logger.info('Start first solve')
    steam_lca.model.solve('design')

    #2. Run: 

    muw.set_attr(T=None)
    muw.set_attr(T=Ref(c0_3, 1, -20))
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

        muw3.set_attr(m=Ref(c_trap_waste, 1, 0), T=steam_lca.params['Tamb'],
                      fluid={"H2O": 1}, 
                      )
        logger.info('Start third solve')
        steam_lca.model.solve('design')
        steam_lca.trap =True

