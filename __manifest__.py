{
    'name': 'Planificación de Producción - Hexágonos Mexicanos',
    'version': '18.0.1.0.0',
    'category': 'Manufacturing/Planning',
    'summary': 'Módulo de planificación de producción basado en demanda y listas de materiales',
    'description': """
        Módulo independiente de planificación de producción para Hexágonos Mexicanos.
        
        Funcionalidades:
        - Reporte de demanda desde órdenes de venta confirmadas
        - Explosión multinivel de listas de materiales (BOM)
        - Consolidación de demanda por producto semi-elaborado y materia prima
        - Análisis por almacén
        - Comparativa demanda vs inventario disponible
        - Exportación a Excel
        - Dashboard de KPIs de planificación
    """,
    'author': 'Alphaqueb Consulting',
    'website': 'https://www.alphaqueb.com',
    'depends': [
        'sale_management',
        'stock',
        'mrp',
    ],
    'data': [
        'security/planning_security.xml',
        'security/ir.model.access.csv',
        'data/planning_data.xml',
        'views/planning_menuitem.xml',
        'views/demand_report_views.xml',
        'views/bom_explosion_views.xml',
        'views/planning_snapshot_views.xml',
        'views/planning_dashboard_views.xml',
        'wizard/generate_demand_wizard_views.xml',
        'wizard/explode_bom_wizard_views.xml',
        'wizard/export_demand_wizard_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'hexagonos_production_planning/static/src/css/planning.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
    'icon': '/hexagonos_production_planning/static/description/icon.png',
}
