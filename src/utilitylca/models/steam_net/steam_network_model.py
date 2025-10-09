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
    
    logging.basicConfig(filename='logs.log', level=logging.INFO)
    steam_lca.cond_inj = False
    steam_lca.trap=False
    steam_lca.converged =False

    steam_lca.model.set_attr(iterinfo=False)
    steam_lca.model.units.set_defaults(temperature='degC', pressure='bar', enthalpy='kJ / kg')
    # create components
    boiler = SimpleHeatExchanger('steam boiler' , dissipative=False)
    bpt = Turbine('back pressure turbine')
    pipe_warm =  Pipe('steam pipe', dissipative=True)
    cond_trap= DropletSeparator('condensate trap')
    valve = Valve('controlvalve')
    hex_heat_sink = SimpleHeatExchanger('hex heat sink', dissipative=False)
    pipe_cold= Pipe('condensate pipe',dissipative=True)
    feed_pump= Pump('feedpump')
    cycl=CycleCloser('CycleCloser')
    
    steam_losses = Sink('steam losses')
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

    dummy_sink2= Sink('dummy sink2')
    injection_source =Source('injection_source')

    #create connections:
    c05 = Connection(cycl, 'out1', boiler, 'in1', label='c05')
    c04 = Connection(boiler, 'out1', bpt, 'in1', label='c04')
    c03 = Connection(bpt, 'out1', pipe_warm, 'in1', label='c03')
    c022= Connection(pipe_warm, 'out1', steam_leak, 'in1', label='c022')
    c02 = Connection(steam_leak, 'out1', valve, 'in1',label='c02')

    c_leak = Connection(steam_leak, 'out2', steam_losses, 'in1', label='c_leak')
    muw2 = Connection(makeup_leak, 'out1', merge, 'in3', label='muw2')

    c01= Connection(valve, 'out1', hex_heat_sink, 'in1', label='c01')
    c1 = Connection(hex_heat_sink, 'out1', pipe_cold, 'in1', label='c1')
    c2 = Connection(pipe_cold, 'out1', split, 'in1', label='c2')
    c3 = Connection(split, 'out1', merge, 'in1', label='c3')
    c4 = Connection(merge, 'out1', feed_pump, 'in1', label='c4')
    c5 = Connection(feed_pump, 'out1', cycl, 'in1', label='c5')

    muw = Connection(makeup, 'out1', merge, 'in2', label='muw')
    wawa = Connection(split, 'out2', blowdown, 'in1', 'c_blowdown')

    steam_lca.model.add_conns(c05, c04, c03, c022, c02, c01, 
                c_leak, 
                c1, c2, c3, c4, c5, 
                muw, wawa, muw2)
    #set attributes:
    boiler.set_attr(pr = 1, power_connector_location="inlet")
    c04.set_attr(fluid={"H2O": 1}, 
                    h= steam_lca.h_superheating_max_pressure)
    c05.set_attr(p0=steam_lca.main_pressure,)
    bpt.set_attr(eta_s = 0.85, )
    c03.set_attr(p=steam_lca.main_pressure, 
                 h0=steam_lca.h_superheating_max_pressure, 
                 )
    pipe_warm.set_attr(pr=0.98, 
        Tamb = steam_lca.params['Tamb'], 
        L=steam_lca.params['pipe_length'], 
        D='var',  
        ks=4.57e-5,
        power_connector_location="outlet",
        insulation_thickness=steam_lca.params['insulation_thickness'] ,
        insulation_tc= 0.035, pipe_thickness=0.004,material='Steel', 
        wind_velocity=steam_lca.params['wind_velocity'], environment_media = steam_lca.params['environment_media']
            ) 
    c_leak.set_attr(m=Ref(c022, steam_lca.params['leakage_factor'], 0))
    c01.set_attr(p = steam_lca.needed_pressure,
                 h0=steam_lca.h_superheating_max_pressure,
                 )
    hex_heat_sink.set_attr(pr=1,Q=-steam_lca.params['heat'], power_connector_location="outlet")
    c1.set_attr(x=0,
                p0=steam_lca.needed_pressure,
                )
    pipe_cold.set_attr(pr=0.95, 
        Tamb = steam_lca.params['Tamb'],
        L=steam_lca.params['pipe_length'], D='var',  ks=4.57e-5,
        power_connector_location="outlet",
        insulation_thickness=steam_lca.params['insulation_thickness'] ,
        insulation_tc= 0.035, 
        pipe_thickness=0.004,material='Steel', 
        wind_velocity= steam_lca.params['wind_velocity'], environment_media = steam_lca.params['environment_media']
            )

    c4.set_attr(p0=steam_lca.needed_pressure,
                )
    
    c5.set_attr(p=steam_lca.params['max_pressure'], 
                h0=steam_lca.h_superheating_max_pressure,
                )

    muw.set_attr(m=Ref(c04, steam_lca.params['makeup_factor'], 0), 
                    T=steam_lca.params['Tamb'],
                    fluid={"H2O": 1},  
                    p0=steam_lca.needed_pressure)
    muw2.set_attr(m=Ref(c_leak, 1, 0), 
                    T=steam_lca.params['Tamb'],
                    fluid={"H2O": 1}, 
                    p0=steam_lca.needed_pressure)
    
    wawa.set_attr(m=Ref(c04, steam_lca.params['makeup_factor'], 0))
    feed_pump.set_attr(eta_s =0.95)
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

    pump_psource = PowerSource('feedpump powersource')
    e_pump = PowerConnection(pump_psource, 'power', feed_pump, 'power', label='e_pump')


    steam_lca.model.add_conns(e_boil,
        e_turb,e_turb_grid,
                           e_pi_c, e_pi_h, e_pi_sink,
                           e_heat_sink, 
                           e_pump
    )
    logger.info('Start first solve')
    steam_lca.model.solve('design')

    #2. Run: 

    muw.set_attr(T=None)
    muw.set_attr(T=Ref(c2, 1, -20))
    logger.info('Start second solve')
    steam_lca.model.solve('design')

    #3. Run: implement condensate injection:
   
    if c022.x.val in [-1,1] :
        steam_lca.model.del_conns(c01, c1)
        c01= Connection(valve, 'out1', merge_injection, 'in1', label='c01')
        cond_3 = Connection(injection_source, 'out1', merge_injection, 'in2')
        cond_5 = Connection(merge_injection, 'out1', hex_heat_sink, 'in1', label= 'cond_5')

        cond_1 = Connection(hex_heat_sink, 'out1', condensate_split, 'in1', label='cond_1')
        cond_2 = Connection(condensate_split, 'out2', dummy_sink2, 'in1')
        c1 = Connection(condensate_split, 'out1', pipe_cold, 'in1', label='c1')
        steam_lca.model.add_conns(cond_1, cond_2, cond_3,cond_5,c01,c1)

        c01.set_attr(p = steam_lca.needed_pressure)
        cond_1.set_attr(x=0)
        c1.set_attr(m=Ref(c01,1,0))
        cond_3.set_attr(x=0, 
                        fluid={"H2O": 1}, 
                        )
        cond_5.set_attr(x=1)
        logger.info('Start third solve')
        steam_lca.model.solve('design')
        steam_lca.cond_inj =True
    
    elif 0< c022.x.val <1:
        merge.set_attr(num_in=4)
        steam_lca.model.del_conns(c02)
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

