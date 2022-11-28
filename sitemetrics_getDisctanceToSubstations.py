# Esri start of added imports
import sys, os, arcpy
from arcgis.gis import GIS
from arcgis.features import find_locations
from arcgis.features.summarize_data import summarize_within
import pandas as pd
try:
    parcelsBuildableUnionItemName = arcpy.GetParameterAsText(0)
    runid = arcpy.GetParameterAsText(1)
    parcelsIDField = arcpy.GetParameterAsText(2)
    parcelsBuildableUnionIDField = arcpy.GetParameterAsText(3)
    vectorItemName = arcpy.GetParameterAsText(4)
    vectorFieldPrefix = arcpy.GetParameterAsText(5)
    vectorWhereClause = arcpy.GetParameterAsText(6)

    # # ###    # debug only  *****************************
    # parcelsBuildableUnionItemName = 'sitemetrics_parcels_buildable_union'  # Not possible to use the ID because the layer is recreated every time the tool runs
    # runid = '30f92219-0bad-40f1-801a-0e1f52dbf9fd'
    # parcelsIDField = 'parcelid'
    # parcelsBuildableUnionIDField = 'parcel_bld_id'
    # vectorItemName = '1db6910429d14a60bebae24cc87648d5'  # this is the fema as feature layer
    # # vectorItemName = '1a58e6becd2d4ba4bb8c401997bebe29' # this is the fema as map image
    # vectorFieldPrefix = 'F500'
    # # vectorWhereClause = "FLD_ZONE in ('A', 'A99', 'AE', 'AH', 'AO')"
    # vectorWhereClause = "FLD_ZONE in ('X')"
    # # vectorWhereClause = ''

    # # ####    # debug only end  *****************************
    # generalTimer = Timer()
    # generalTimer.start()
    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")
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

    # Selecting vector data
    if vectorWhereClause and vectorWhereClause != "":
        arcpy.AddMessage('Selecting vector data')
        try:
            selected_vector_layer = find_locations.derive_new_locations(input_layers=[vectorLyr],
                                                                        expressions=[{"operator": "", "layer": 0,
                                                                                      "where": vectorWhereClause}],
                                                                        context=context)
            vectorLyr = selected_vector_layer

            # check that vectorLyr has features
            featureSet_arcgis = vectorLyr.query()
            if len(featureSet_arcgis.features) == 0:
                raise Exception

        except Exception as e:
            print (e)
            # return an empty dataset
            data_json = f'''{{
             "objectIdFieldName": "OBJECTID",
             "fields": [
              {{
               "name": "OBJECTID", "alias": "OBJECTID", "type": "esriFieldTypeOID"
              }},
              {{
               "name": "parcelid", "alias": "parcelid", "type": "esriFieldTypeString"
              }},
              {{
               "name": '{vectorFieldPrefix}_Acres', "alias": '{vectorFieldPrefix}_Acres', "type": "esriFieldTypeInteger"
              }},
              {{
               "name": '{vectorFieldPrefix}_BL_Acres', "alias": '{vectorFieldPrefix}_BL_Acres', "type": "esriFieldTypeInteger"
              }},
              {{
               "name": '{vectorFieldPrefix}_Pcnt', "alias": '{vectorFieldPrefix}_Pcnt', "type": "esriFieldTypeInteger"
              }},
              {{
               "name": '{vectorFieldPrefix}_BL_Pcnt', "alias": '{vectorFieldPrefix}_BL_Pcnt', "type": "esriFieldTypeInteger"
              }}
             ],
             "features": [
              {{
               "attributes": {{
                "OBJECTID": 1,
                "parcelid": "1",
                '{vectorFieldPrefix}_Acres': 0,
                '{vectorFieldPrefix}_BL_Acres': 0,
                '{vectorFieldPrefix}_Pcnt': 0,
                '{vectorFieldPrefix}_BL_Pcnt': 0
               }}
              }}
             ]
            }}
            '''

            recSet = arcpy.RecordSet(data_json)

            # set the responses
            arcpy.SetParameter(7, recSet)
            textResponse = f"### {vectorFieldPrefix} COMPLETED SUCCESSFULLY BECAUSE I ROCK ### "
            arcpy.AddMessage(textResponse)
            arcpy.SetParameterAsText(8, str(textResponse))
            sys.exit()

        #
        # {"messageCode": "AO_100024",
        #  "message": "There are no features provided for analysis in FEMA Flood Hazard Areas (100yr/500yr).",
        #  "params": {"inputLayer": "FEMA Flood Hazard Areas (100yr/500yr)"}}
        # {"messageCode": "AO_100049", "message": "There are no features in the processing extent for any input layers."}
        # {"messageCode": "AO_100079", "message": "DeriveNewLocations failed."}
        # Failed to execute(DeriveNewLocations).

    arcpy.AddMessage('Summarizing data')

    statsWithinParcelBld = summarize_within(sum_within_layer=zoneFLyr,
                                            summary_layer=vectorLyr,
                                            sum_shape=True,
                                            shape_units='Acres',
                                            summary_fields=[],
                                            group_by_field=None,
                                            minority_majority=False,
                                            percent_shape=True,
                                            context=context)

    # Getting the stats
    statsDF = statsWithinParcelBld.query().sdf
    # delete the summarize portal item
    if vectorWhereClause and vectorWhereClause != "":
        # selected_vector_layer.delete()
        del selected_vector_layer
    # statsWithinParcelBld.delete()
    del statsWithinParcelBld
    # areas of area per parcel
    zone_sdf = zoneFLyr.query().sdf
    parcelAreasDF = zone_sdf.groupby([parcelsIDField]).analysisarea.sum().reset_index()
    parcelAreasDF[f'Parcel_Acres'] = parcelAreasDF['analysisarea'].multiply(640)
    parcelAreasDF.drop(columns=['analysisarea'], inplace=True)
    # areas of buildable per parcel
    parcelBLAreasDF = zone_sdf[zone_sdf[parcelsBuildableUnionIDField].str.endswith('_1')].groupby(
        [parcelsIDField]).analysisarea.sum().reset_index()
    parcelBLAreasDF[f'BL_Acres'] = parcelBLAreasDF['analysisarea'].multiply(640)
    parcelBLAreasDF.drop(columns=['analysisarea'], inplace=True)
    parcelAreasDF = pd.merge(parcelAreasDF, parcelBLAreasDF, on=parcelsIDField, how='left')
    # summarize area by parcelsBuildableUnionIDField
    summarize_df = statsDF.groupby([parcelsIDField, parcelsBuildableUnionIDField]).sum_Area_Acres.sum().reset_index()
    # pivot table to convert parcelsBuildableUnionIDField to parcelid
    summarize_df['buildableIndex'] = summarize_df[parcelsBuildableUnionIDField].str[-1:]
    tmp_pivot_table = summarize_df.pivot_table(index='parcelid', columns='buildableIndex', values='sum_Area_Acres')
    tmp_pivot_table.reset_index(inplace=True)
    # total acres
    tmp_pivot_table[f'{vectorFieldPrefix}_Acres'] = (tmp_pivot_table['0'] + tmp_pivot_table['1'])
    # vector acres in buildable
    tmp_pivot_table[f'{vectorFieldPrefix}_BL_Acres'] = tmp_pivot_table['1']
    # fix fields
    tmp_pivot_table.drop(columns=['0', '1'], inplace=True)
    # bring in the total parcel area
    tmp_pivot_table = pd.merge(tmp_pivot_table, parcelAreasDF, on=parcelsIDField, how='left')
    # calculate percentages
    tmp_pivot_table[f'{vectorFieldPrefix}_Pcnt'] = tmp_pivot_table[f'{vectorFieldPrefix}_Acres'] / \
                                                   tmp_pivot_table['Parcel_Acres'] * 100.0
    tmp_pivot_table[f'{vectorFieldPrefix}_BL_Pcnt'] = tmp_pivot_table[
                                                          f'{vectorFieldPrefix}_BL_Acres'] / \
                                                      tmp_pivot_table['BL_Acres'] * 100.0
    # drop redundant fields that are already in the main program
    tmp_pivot_table.drop(columns=['Parcel_Acres', 'BL_Acres'], inplace=True)
    tmp_pivot_table.fillna(0, inplace=True)
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
