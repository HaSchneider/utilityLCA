from tespy.components import (
    Turbine, Source, Sink, Pump, Compressor,Condenser,
    Pipe, CycleCloser, SimpleHeatExchanger, Valve, Merge, HeatExchanger, Motor,
    Splitter, 
    DropletSeparator,
    PowerSink, PowerSource, Generator,  PowerBus, 
    HeatSink, HeatSource, HeatBus,PowerBus,
    Subsystem
)
from tespy.networks import Network

from tespy.connections import Connection, Ref, PowerConnection, HeatConnection
import logging

#logger = logging.getLogger(__name__)
def create_hp_subsystem(heatpumps_path):

    hp_net= Network().from_json(heatpumps_path)
    powerbus_index= hp_net.get_comp('Power Distribution').power_outl.index(hp_net.get_conn('E_cons_pump_in'))
    hp_net.del_conns(hp_net.get_conn('C0'), hp_net.get_conn('C1'), hp_net.get_conn('C2'), hp_net.get_conn('C3'),
                     hp_net.get_conn('E_cons_pump_in'), hp_net.get_conn('E_cons_pump_out'))
    #comps
    motor_mvr = Motor('mvr_motor')
    mvr = Compressor('mvr')
    cons_source=Source('consumer source')
    cons_sink= Sink('consumer sink')
    C0 = Connection(cons_source, 'out1', hp_net.get_comp('Condenser'), 'in2', 'C0')
    C1 = Connection(hp_net.get_comp('Condenser'), 'out2', mvr, 'in1', 'C1')
    C2 = Connection(mvr, 'out1', cons_sink, 'in1', 'C2')
    hp_net.add_conns(C0, C1, C2)
    C1.set_attr(x=1)
    pc_motor_mvr = PowerConnection(hp_net.get_comp('Power Distribution'), f'power_out{powerbus_index+1}',
                motor_mvr, 'power_in', f'E_mvr_motor')
    pc_mvr = PowerConnection(motor_mvr, 'power_out', mvr, 'power',f'E_mvr')
    hp_net.add_conns(pc_mvr, pc_motor_mvr)
    
    mvr.set_attr(eta_s=0.8)
    motor_mvr.set_attr(eta=0.9)

    hp_sub= hp_net.convert_to_subsystem('hp_sub', 
                                        ['Heat Source Back Flow',
                                         'Heat Source Feed Flow'])
    '''
    class hp_subsystem(Subsystem):
        def __init__(self, label):
            self.num_in = 1
            self.num_out = 1
            self.num_power_in = 1
            super().__init__(label)

        def create_network(self):
            mvr=Compressor('mvr')
            heat_source_feed = Source('Heat_source_feed')
            heat_source_return = Sink('Heat_source_return')
            hp= hp_sub('hp')
            #powerbus= PowerBus('PowerBus', num_in=1, num_out=3)
            
            c_cold = Connection(self.inlet, "out1", hp.inlet, "in1", label="c_cold")
            c_mvr= Connection(hp.outlet, "out1", mvr, "in1", label="c_mvr")
            c_hot = Connection(mvr, "out1", self.outlet, "in1", label="c_hot")
            
            #pc_hp = PowerConnection(powerbus, "power_out1", hp.inlet, 'power_out1', label='hp_power')
            #pc_mvr = PowerConnection(powerbus, "power_out2", mvr, 'power', label='mvr_power')
            pc_total = PowerConnection(self.inlet, "power_in1", powerbus, 'power_in1', label='total_power')
            
            c_h_f = Connection(heat_source_feed, "out1", hp.inlet, "in2", label="c_heat_source_feed")
            c_h_r= Connection(hp.outlet, "out2", heat_source_return, "in1", label="c_heat_source_return")
             

            self.add_conns(c_hot,c_mvr, c_cold,
                           pc_hp, pc_mvr, pc_total,
                           c_h_r, c_h_f)
    '''
    return hp_sub
class hp_subsystem(Subsystem):
    def __init__(self, label):
        self.num_in = 1
        self.num_out = 1
        self.num_power_in =1
        super().__init__(label)
        self.comps={}
    def create_network(self):
        self.comps['hs_ff'] = Source('Heat Source Feed Flow')
        self.comps['hs_bf'] = Sink('Heat Source Back Flow')
        self.comps['hs_pump'] = Pump('Heat Source Recirculation Pump')

        # Heat sink
        self.comps['mvr'] = Compressor('mvr')

        # Main cycle
        self.comps['cond'] = Condenser('Condenser')
        self.comps['cc'] = CycleCloser('Main Cycle Closer')
        self.comps['valve'] = Valve('Valve')
        self.comps['evap'] = HeatExchanger('Evaporator')
        self.comps['comp'] = Compressor('Compressor')

        # Power input
        self.comps['power_distribution'] = PowerBus('Power Distribution', num_in=1, num_out=3)
        self.comps['motor_comp'] = Motor(self.comps['comp'].label + ' Motor')
        self.comps['motor_hs_pump'] = Motor(self.comps['hs_pump'].label + ' Motor')
        self.comps['motor_mvr'] = Motor(self.comps['mvr'].label + ' Motor')

        #def generate_connections(self):
        """Initialize and add connections and power connections to network."""
        # Connections
        self.conns['A0'] = Connection(self.comps['cond'], 'out1', self.comps['cc'], 'in1', 'A0')
        self.conns['A1'] = Connection(self.comps['cc'], 'out1', self.comps['valve'], 'in1', 'A1')
        self.conns['A2'] = Connection(self.comps['valve'], 'out1', self.comps['evap'], 'in2', 'A2')
        self.conns['A3'] = Connection(self.comps['evap'], 'out2', self.comps['comp'], 'in1', 'A3')
        self.conns['A4'] = Connection(self.comps['comp'], 'out1', self.comps['cond'], 'in1', 'A4')

        self.conns['B1'] = Connection(self.comps['hs_ff'], 'out1', self.comps['evap'], 'in1', 'B1')
        self.conns['B2'] = Connection(self.comps['evap'], 'out1', self.comps['hs_pump'], 'in1', 'B2')
        self.conns['B3'] = Connection(self.comps['hs_pump'], 'out1', self.comps['hs_bf'], 'in1', 'B3')

        self.conns['C0'] = Connection(self.inlet, 'out1', self.comps['cond'], 'in2', 'C0')
        self.conns['C1'] = Connection(self.comps['cond'], 'out2', self.comps['mvr'], 'in1', 'C1')
        self.conns['C2'] = Connection(self.comps['mvr'], 'out1', self.outlet, 'in1', 'C2')

        self.nw.add_conns(*[conn for conn in self.conns.values()])

        rotating_comps = ['comp', 'hs_pump', 'mvr']
        power_conns = [
            PowerConnection(
                self.comps['grid'], 'power',
                self.comps['power_distribution'], 'power_in1',
                'E_grid'
                )
            ]
        self.conns['E_grid'] = power_conns[0]
        for i, key in enumerate(rotating_comps, start=1):
            motor = self.comps[f'motor_{key}']
            motor.set_attr(eta=0.98)
            conn_in = PowerConnection(
                self.comps['power_distribution'], f'power_out{i}',
                motor, 'power_in', f'E_{key}_in'
                )
            conn_out = PowerConnection(
                motor, 'power_out', self.comps[key], 'power',
                f'E_{key}_out'
                )
            self.conns[f'E_{key}_in'] = conn_in
            self.conns[f'E_{key}_out'] = conn_out
            power_conns += [conn_in, conn_out]

        self.nw.add_conns(*power_conns)

class conv_subsystem(Subsystem):
    #electricity missing
    def __init__(self, label):
        self.num_in = 1
        self.num_out = 1
        self.num_power_in =1
        super().__init__(label)
    def create_network(self):
        hex=SimpleHeatExchanger('boiler', dissipative=False, pr=1 )
        c_cold = Connection(self.inlet, "out1", hex, "in1", label="c_cold")
        c_hot = Connection(hex, "out1", self.outlet, "in1", label="c_hot")
        heat=PowerConnection(self.inlet, "power_out1", hex, 'heat', label= 'e_boil')
        self.add_conns(c_hot, c_cold, heat)


def create_steam_net(steam_lca, boiler_subsystem, chp= True):
    
    #logging.basicConfig(filename='steam_log.log', 
    #                    filemode="w",
    #                    level=logging.INFO)

    steam_lca.model.iterinfo=True
    steam_lca.model.units.set_defaults(temperature='degC', 
                                       pressure_difference='bar', enthalpy='kJ / kg')
    # create components
    boiler = boiler_subsystem('steam boiler')
    steam_lca.model.add_subsystems(boiler)
    
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
    if chp:
        #components
        bpt = Turbine('back pressure turbine')
        #connections
        c1_6 = Connection(boiler, 'out1', bpt, 'in1', label='c1_6') #c04
        c1_5 = Connection(bpt, 'out1', pipe_warm, 'in1', label='c1_5') #c03
        steam_lca.model.add_conns(c1_6, c1_5,)
    else:
        c1_6 = Connection(boiler, 'out1', pipe_warm, 'in1', label='c1_5') #c03
        steam_lca.model.add_conns(c1_6,)

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

    steam_lca.model.add_conns(c1_4, c1_3, c1_2, c1_1, 
                              cnw1, cnw2,cnw3,
                              c_leak,
                              c0_11,
                              c0_1, c0_2, c0_3, c0_4, c0_5, c0_6, c0_7,
                              muw, wawa, muw2)
    #set attributes:
    boiler.set_attr(pr = 1, #power_connector_location="inlet"
                    )
    c1_6.set_attr(fluid={"water": 1}, 
                    h= steam_lca.h_superheating_max_pressure)
    if chp:
        bpt.set_attr(eta_s = 0.85, )
        c1_5.set_attr(p=steam_lca.main_pressure, 
                 h0=steam_lca.h_superheating_max_pressure,)
        c0_6.set_attr(p=steam_lca.parameters['max_pressure'].default, 
                h0=steam_lca.h_superheating_max_pressure,)
    else:
        c0_6.set_attr(p=steam_lca.main_pressure)
    pipe_warm.set_attr(pr=0.95, 
        Tamb = steam_lca.parameters['Tamb'].default, 
        L=steam_lca.parameters['pipe_length'].default, 
        D='var', ks=4.57e-5,
        #power_connector_location="outlet",
        #power_connector_location="outlet",
        insulation_thickness=steam_lca.parameters['insulation_thickness'].default ,
        insulation_tc= 0.035, pipe_thickness=0.004,material='Steel', 
        wind_velocity=steam_lca.parameters['wind_velocity'].default, 
        environment_media = steam_lca.parameters['environment_media'].default
            ) 
    c_leak.set_attr(m=Ref(c1_4, steam_lca.parameters['leakage_factor'].default, 0))
    c1_1.set_attr(p = steam_lca.needed_pressure,
                 h0=steam_lca.h_superheating_max_pressure,
                 )
    hex_heat_sink.set_attr(pr=1,
                           Q=-steam_lca.parameters['heat'].default, 
                           #power_connector_location="outlet"
                           )
                           #power_connector_location="outlet"
                           )
    
    
    c0_2.set_attr(p=steam_lca.main_pressure 
                )
    pipe_cold.set_attr(pr=0.95, 
        Tamb = steam_lca.parameters['Tamb'].default,
        L=steam_lca.parameters['pipe_length'].default, D='var',  ks=4.57e-5,
        #power_connector_location="outlet",
        #power_connector_location="outlet",
        insulation_thickness=steam_lca.parameters['insulation_thickness'].default ,
        insulation_tc= 0.035, 
        pipe_thickness=0.004,material='Steel', 
        wind_velocity= steam_lca.parameters['wind_velocity'].default, 
        environment_media = steam_lca.parameters['environment_media'].default
            )

    c0_5.set_attr(p0=steam_lca.needed_pressure,)

    muw.set_attr(m=Ref(c1_6, steam_lca.parameters['makeup_factor'].default, 0), 
                    T=steam_lca.parameters['Tamb'].default,
                    fluid={"water": 1},  
                    p0=1.013)
    muw2.set_attr(m=Ref(c_leak, 1, 0), 
                    T=steam_lca.parameters['Tamb'].default,
                    fluid={"water": 1}, 
                    p0=1.013)
    
    wawa.set_attr(m=Ref(c1_6, steam_lca.parameters['makeup_factor'].default, 0))
    feed_pump.set_attr(eta_s =0.95)
    condensate_pump.set_attr(eta_s=0.95)
    network_heat_sink.set_attr(pr=1, 
                               Q=-(steam_lca.parameters['heat_capacity_pipe_network'].default-steam_lca.parameters['heat'].default),
                               #power_connector_location="outlet",
                               #power_connector_location="outlet",
                               )
    cnw2.set_attr(x=0)
    c0_1.set_attr(x=0)
    
    # create power connections:
    
    fuel_bus = PowerSource('boiler energysource')
    #if steam_lca.paras['heat_source']=='conv':
    #    e_boil = PowerConnection(fuel_bus, 'power', boiler.inlet, 'heat_in1', label= 'e_boil2')
    #elif steam_lca.paras['heat_source']=='hp':
    e_boil = PowerConnection(fuel_bus, 'power', boiler.inlet, 'power_in1', label= 'e_boil2')
    
    turbine_gen = Generator('turbines')
    turbine_gen.set_attr(eta= 0.9)
    turbine_grid = PowerSink('grid')
    if chp:
        e_turb = PowerConnection(bpt, 'power', turbine_gen, 'power_in', label='e_turb')
        steam_lca.model.add_conns(e_turb)
    e_turb_grid =PowerConnection(turbine_gen, 'power_out', turbine_grid, 'power', 
                                label='e_turb_grid')

    pipe_diss_sink =HeatSink('pipe dissipative losses sink')
    pipe_diss_bus = HeatBus('pipe dissipative losses bus', num_in =2, num_out=1)

    e_pi_h = HeatConnection(pipe_warm, 'heat', pipe_diss_bus, 'heat_in1')
    e_pi_c = HeatConnection(pipe_cold, 'heat', pipe_diss_bus, 'heat_in2')
    e_pi_sink = HeatConnection(pipe_diss_bus, 'heat_out1', pipe_diss_sink, 'heat', label='e_pi_sink')
    
    heat_sink =HeatSink('heat sink')
    e_heat_sink =HeatConnection( hex_heat_sink,'heat',heat_sink, 'heat', label='e_heat_sink')

    nw_heat_sink =HeatSink('nw heat sink')
    e_nw_heat_sink =HeatConnection( network_heat_sink,'heat',nw_heat_sink, 'heat', label='e_nw_heat_sink')

    pump_psource = PowerSource('feedpump powersource')
    e_pump = PowerConnection(pump_psource, 'power', feed_pump, 'power', label='e_pump')


    steam_lca.model.add_conns(e_boil,
                            e_turb_grid,
                           e_pi_c, e_pi_h, e_pi_sink,
                           e_heat_sink, e_nw_heat_sink,
                           e_pump
    )
    #logger.info('Start first solve')
    steam_lca.model.solve('design')
    #logger.info('First solve successfull')
    #2. Run: 

    muw.set_attr(T=None)
    muw.set_attr(T=Ref(c0_3, 1, -20))
    #logger.info('Start second solve')
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
                        fluid={"water": 1}, 
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
                      fluid={"water": 1}, 
                      )
        #slogger.info('Start third solve')
        steam_lca.model.solve('design')
        steam_lca.trap =True

