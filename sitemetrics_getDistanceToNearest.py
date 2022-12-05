# Esri start of added imports
import sys, os, arcpy
from arcgis.gis import GIS
from arcgis.features.use_proximity import find_nearest

import pandas as pd
try:

    parcelsItemID = arcpy.GetParameterAsText(0)
    runid = arcpy.GetParameterAsText(1)
    parcelsIDField = arcpy.GetParameterAsText(2)
    proximityItemID = arcpy.GetParameterAsText(3)
    proximitySubLayerID = arcpy.GetParameterAsText(4)
    proximityFieldPrefix = arcpy.GetParameterAsText(5)

    # ###    # debug only  *****************************
    parcelsItemID = 'a9ac200342824bcd8626dbe9f816ef4d'  # site_metrics_inputParcels
    # parcelsItemID = 'c52edce5c4324efea8383604903918ab'  # site_metrics_inputParcelsDEV

    runid = '30f92219-0bad-40f1-801a-0e1f52dbf9fd'
    parcelsIDField = 'parcelid'
    proximityItemID = 'b3afb2c9f69a47cc8a3ddc9571c84856'  # Transmission_Lines_from_Velocity_Suite
    proximitySubLayerID = 1  # this is proposed transmission lines
    proximityFieldPrefix = 'PropTrans'
    # ####    # debug only end  *****************************


    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")

    # find the site metric parcels and proximity layers (site_metrics_inputParcels)
    t0 = time.time()
    inputParcelsItem = gis.content.get(parcelsItemID)
    inputParcelsLyr = inputParcelsItem.layers[0]
    proximityItem = gis.content.get(proximityItemID)
    proximityLyr = proximityItem.layers[proximitySubLayerID]
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1-t0)}")

    # DO NOT use context because the proximity features also need to be within the context
    # # creating context object and send to image server
    # inputParcelsSDF = inputParcelsLyr.query("1=1").sdf
    # # inputParcelsLyr.properties.extent gives a wrong extent
    # inputParcelsWKID = inputParcelsSDF.spatial.sr['wkid']
    # inParcelsExtent = inputParcelsSDF.spatial.full_extent
    # context = {"extent": {"xmin": inParcelsExtent[0],
    #                       "ymin": inParcelsExtent[1],
    #                       "xmax": inParcelsExtent[2],
    #                       "ymax": inParcelsExtent[3],
    #                       "spatialReference": {"wkid": inputParcelsWKID}},
    #            "overwrite": True
    #            }



    try:
        nearestItem = find_nearest(analysis_layer=inputParcelsLyr,
                                     near_layer=proximityLyr,
                                     measurement_type="StraightLine",
                                     max_count="1",
                                     search_cutoff=30,
                                     search_cutoff_units="Miles",
                                     output_name=f"sitemetrics_nearest_{proximityFieldPrefix}")
    except Exception as e:
        try:
            nearestItem.delete()
        except Exception as e:
            arcpy.AddMessage(f'Problem creating the sitemetrics_nearest_{proximityFieldPrefix} layer')
            sys.exit()

    print("done")
    nearestLyr = nearestItem.layers[1]
    nearestSDF = nearestLyr.query('1=1').sdf
    nearestSDF = nearestSDF[['from_parcelid', 'total_miles']]
    nearestSDF.rename(columns={'total_miles': f'{proximityFieldPrefix}_miles'}, inplace=True)

    # delete the nearestItem from geoportal
    nearestItem.delete()

    print("ok")
    sys.exit()




    # find the zone layer
    arcpy.AddMessage('Getting all GIS info')
    zoneItem = gis.content.search(parcelsBuildableUnionItemName, 'feature layer')[0]
    zoneFLyr = zoneItem.layers[0]
    # find the vector layer
    vectorItem = gis.content.get(vectorItemName)
    vectorLyr = vectorItem.layers[0]
    from arcgis.geometry import *
    envelope = Envelope(zoneItem.extent)
    XMin = envelope.x[0]
    YMin = envelope.x[1]
    XMax = envelope.y[0]
    YMax = envelope.y[1]
    context = {"extent": {"xmin": XMin,
                          "ymin": YMin,
                          "xmax": XMax,
                          "ymax": YMax,
                          "outSR": {"wkid": int(zoneItem.spatialReference)},
                          "overwrite": True}}

    # # Selecting vector data
    # if vectorWhereClause and vectorWhereClause != "":
    #     arcpy.AddMessage('Selecting vector data')
    #     try:
    #         selected_vector_layer = find_locations.derive_new_locations(input_layers=[vectorLyr],
    #                                                                     expressions=[{"operator": "", "layer": 0,
    #                                                                                   "where": vectorWhereClause}],
    #                                                                     context=context)
    #         vectorLyr = selected_vector_layer
    #
    #         # check that vectorLyr has features
    #         featureSet_arcgis = vectorLyr.query()
    #         if len(featureSet_arcgis.features) == 0:
    #             raise Exception
    #
    #     except Exception as e:
    #         print (e)
    #         # return an empty dataset
    #         data_json = f'''{{
    #          "objectIdFieldName": "OBJECTID",
    #          "fields": [
    #           {{
    #            "name": "OBJECTID", "alias": "OBJECTID", "type": "esriFieldTypeOID"
    #           }},
    #           {{
    #            "name": "parcelid", "alias": "parcelid", "type": "esriFieldTypeString"
    #           }},
    #           {{
    #            "name": '{vectorFieldPrefix}_Acres', "alias": '{vectorFieldPrefix}_Acres', "type": "esriFieldTypeInteger"
    #           }},
    #           {{
    #            "name": '{vectorFieldPrefix}_BL_Acres', "alias": '{vectorFieldPrefix}_BL_Acres', "type": "esriFieldTypeInteger"
    #           }},
    #           {{
    #            "name": '{vectorFieldPrefix}_Pcnt', "alias": '{vectorFieldPrefix}_Pcnt', "type": "esriFieldTypeInteger"
    #           }},
    #           {{
    #            "name": '{vectorFieldPrefix}_BL_Pcnt', "alias": '{vectorFieldPrefix}_BL_Pcnt', "type": "esriFieldTypeInteger"
    #           }}
    #          ],
    #          "features": [
    #           {{
    #            "attributes": {{
    #             "OBJECTID": 1,
    #             "parcelid": "1",
    #             '{vectorFieldPrefix}_Acres': 0,
    #             '{vectorFieldPrefix}_BL_Acres': 0,
    #             '{vectorFieldPrefix}_Pcnt': 0,
    #             '{vectorFieldPrefix}_BL_Pcnt': 0
    #            }}
    #           }}
    #          ]
    #         }}
    #         '''
    #
    #         recSet = arcpy.RecordSet(data_json)
    #
    #         # set the responses
    #         arcpy.SetParameter(7, recSet)
    #         textResponse = f"### {vectorFieldPrefix} COMPLETED SUCCESSFULLY BECAUSE I ROCK ### "
    #         arcpy.AddMessage(textResponse)
    #         arcpy.SetParameterAsText(8, str(textResponse))
    #         sys.exit()
    #
    #     #
    #     # {"messageCode": "AO_100024",
    #     #  "message": "There are no features provided for analysis in FEMA Flood Hazard Areas (100yr/500yr).",
    #     #  "params": {"inputLayer": "FEMA Flood Hazard Areas (100yr/500yr)"}}
    #     # {"messageCode": "AO_100049", "message": "There are no features in the processing extent for any input layers."}
    #     # {"messageCode": "AO_100079", "message": "DeriveNewLocations failed."}
    #     # Failed to execute(DeriveNewLocations).
    #
    # arcpy.AddMessage('Summarizing data')
    #
    # statsWithinParcelBld = summarize_within(sum_within_layer=zoneFLyr,
    #                                         summary_layer=vectorLyr,
    #                                         sum_shape=True,
    #                                         shape_units='Acres',
    #                                         summary_fields=[],
    #                                         group_by_field=None,
    #                                         minority_majority=False,
    #                                         percent_shape=True,
    #                                         context=context)

    # return the stats table as a RecordSet without writing to disk
    final_stats_table = tmp_pivot_table.spatial.to_featureset()
    arcpy.AddMessage('Writing to record set')
    recSet = arcpy.RecordSet()
    recSet.load(final_stats_table)
    # set the responses
    arcpy.SetParameter(7, recSet)
    textResponse = f"### {vectorFieldPrefix} COMPLETED SUCCESSFULLY BECAUSE I ROCK ### "
    arcpy.AddMessage(textResponse)
    arcpy.SetParameterAsText(8, str(textResponse))
except arcpy.ExecuteError:
    print('-1-')
    print(arcpy.GetMessages(1))
    print('-2-')
    print(arcpy.GetMessages(2))
    arcpy.AddError('-1-')
    arcpy.AddError(arcpy.GetMessages(1))
    arcpy.AddError('-2-')
    arcpy.AddError(arcpy.GetMessages(2))
    arcpy.SetParameterAsText(5, str(arcpy.GetMessages(1) + "  -  " + arcpy.GetMessages(2)))
except Exception as e:
    print(e)
    arcpy.AddError(e)
    arcpy.SetParameterAsText(5, str(e))
