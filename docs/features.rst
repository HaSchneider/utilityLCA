.. _features:

=================
Features
=================

Parameters
"""""""""""

The following table shows the parameters that can be passed to the steam distribution model:

==========================  ======  =============
Parameter                   Unit    Default value
==========================  ======  =============
Makeup factor               %       5	
Ambient temperature         °C      20	
Leakage factor              %       7.5	
Steam generation pressure   bara    130	
Pipeline capacity           MW      20	
Process heat demand         MW      1	
Wind velocity               m/s     3  	
Insulation thickness        m       0.1	
Environment                         `Air`	
Pipe length                 m       1000	
==========================  ======  =============

Heat pump steam generation
"""""""""""""""""""""""""""

Instead of a heat generation which is based on an extern LCA dataset, a heat pump can be assumed. 
To do so, initiate the model with the argument :code:`heatsource= 'hp'` and provide a path to a heat pump model, exported from the `heatpumps <https://github.com/jfreissmann/heatpumps>`_ package by the argument `heatpump_path`. 
The heat pump model must be exported as a .json file.

.. code-block:: python

    from utilitylca import steam_distribution_model as sdm
    from simodin import interface as link

    my_model= sni.steam_net('steam net', 
                        heatsource='hp',
                        heatpump_path=r'PATH\TO\MODEL\EXPORT\HeatPumpSimple_tespy.json' 
                        )

.. important:: This feature is still under development and not fully tested. Please use with caution. Simple heat pump cycle with amonia as refrigerant should work, but more complex cycles might not be supported.