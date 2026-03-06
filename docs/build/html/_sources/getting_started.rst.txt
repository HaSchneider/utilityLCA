.. _getting_started:

=================
Getting started
=================



Installation
"""""""""""""


Install utilityLCA from PyPi:

.. code-block:: python

   pip install utilityLCA


Example
"""""""""

To get started with utilityLCA, you need to create a steam distribution class. 
Passing a name is mandatory, while the other parameters have default values. 
The following code shows how to create a steam distribution model with custom parameters. 

.. code-block:: python

    from utilitylca import steam_distribution_conventional as sdc
    from simodin import interface as link

    my_model= sdc.steam_net('steam net', needed_temperature= 180, wind_velocity=3, heat=1E6 ,
                        heat_capacity_pipe_network = 20E6,
                        insulation_thickness=0.1
                        )

The full list of parameters and their default values are:

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

The parameters can also be changed later explicitly by:


.. code-block:: python

    my_model.params['needed_temperature']= 200


Or be passed to the init_model or calculate_model method. 
In init_model method, the model is initialized and the parameters are used to set up the model structure.
In calculate_model method, the model is calculated and the parameters are used in the calculation.

.. code-block:: python

    my_model.init_model(wind_velocity=2)
    my_model.calculate_model()

To link LCA datasets to the model, the technosphere flows needs to be generated and the SiModIn interface class created:

.. code-block:: python

    my_model.define_flows()
    my_interface= link.modelInterface('steam_net', my_model)


For LCA calculation, the needed brightway25 dataset needs to be assigned to the technosphere flows.

.. dropdown:: The brightway25 code for searching ecoinvent datasets are shown here.

    .. code-block:: python

        import bw2data as bd

    
        bd.projects.set_current('steam_distribution')
        
        ei=bd.Database('ecoinvent-3.11-cutoff')

        ei_heat=[act for act in ei if 'heat production, at hard coal industrial furnace 1-10MW' in act['name']
        and 'Europe without Switzerland' in act['location'] ][0]

        ei_water=[act for act in ei if 'market for tap water' in act['name']
        and 'Europe without Switzerland' in act['location'] ][0]

        ei_electricity=[act for act in ei if 'market for electricity, medium' in act['name']][0]

        bio=bd.Database('ecoinvent-3.11-biosphere')
        water_bio=bio.get('51254820-3456-4373-b7b4-056cf7b16e01')

Then, the datasets are assigned to the technosphere flows and the impact categories are defined for the impact calculation.

.. code-block:: python

    my_interface.methods=[('ecoinvent-3.11',  'EF v3.1',  'climate change',  'global warming potential (GWP100)')]

    my_interface.add_dataset('steam generation', ei_steam)
    my_interface.add_dataset('electricity grid',ei_electricity)
    my_interface.add_dataset('electricity substitution',ei_electricity)

    my_interface.add_dataset('steam leak',water_bio)


After that, the LCA calculation can be executed or the data exported to a brightway25 database:

.. code-block:: python

    my_interface.calculate_background_impact()
    my_interface.calculate_impact()
    code= my_interface.export_to_bw()

The result can be printed by:

.. code-block:: python

    my_interface.impact_allocated

This returns a dictionary containing the impact scores for all defined impact categories 
refered to one megajoule of heat transferred to the process.


.. code-block:: python
    
    {('ecoinvent-3.10',
    'EF v3.1',
    'climate change',
    'global warming potential (GWP100)'): {'distributed steam': 0.15,
    'network steam': 2.5}}

Substitution is configured by default. To switch to allocation, the electricity flow needs to be set to functional, and the target to None:

.. code-block:: python

    my_model.set_flow_attr('electricity substitution', 'target', None)
    my_model.set_flow_attr('electricity substitution', 'functional',True )

    my_interface.calculate_impact()