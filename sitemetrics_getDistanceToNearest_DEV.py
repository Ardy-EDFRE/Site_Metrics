# Esri start of added imports
import sys, os, arcpy, time
import datetime
from arcgis.gis import GIS
from arcgis.features import find_locations
# from arcgis.features.use_proximity import find_nearest
from arcgis.features.analysis import find_nearest


def setResponses(proximityFieldPrefix, recSet):
    arcpy.SetParameter(7, recSet)
    textResponse = f"### {proximityFieldPrefix} COMPLETED SUCCESSFULLY BECAUSE I ROCK ### "
    arcpy.AddMessage(textResponse)
    arcpy.SetParameterAsText(8, str(textResponse))

def returnEmptyDataset(proximityFieldPrefix):
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
       "name": '{proximityFieldPrefix}_Miles', "alias": '{proximityFieldPrefix}_Miles', "type": "esriFieldTypeDouble"
      }}
     ],
     "features": [
      {{
       "attributes": {{
        "OBJECTID": 1,
        "parcelid": "1",
        '{proximityFieldPrefix}_miles': 0.0
       }}
      }}
     ]
    }}
    '''
    return arcpy.RecordSet(data_json)


try:
    parcelsItemID = arcpy.GetParameterAsText(0)
    runid = arcpy.GetParameterAsText(1)
    parcelsIDField = arcpy.GetParameterAsText(2)
    proximityItemID = arcpy.GetParameterAsText(3)
    proximitySubLayerID = arcpy.GetParameterAsText(4)
    proximityFieldPrefix = arcpy.GetParameterAsText(5)
    whereClause = arcpy.GetParameterAsText(6)

    # ###    # debug only  *****************************
    # # parcelsItemID = 'a9ac200342824bcd8626dbe9f816ef4d'  # site_metrics_inputParcels
    # parcelsItemID = '132c430f3c024fb08cf6368d52a3334a'  # site_metrics_inputParcelsDEV
    # runid = '30f92219-0bad-40f1-801a-0e1f52dbf9fd'
    # parcelsIDField = 'parcelid'

    ## transmission lines
    # proximityItemID = 'b3afb2c9f69a47cc8a3ddc9571c84856'  # Transmission_Lines_from_Velocity_Suite
    # proximitySubLayerID = 0 # this is existing transmission lines
    # proximityFieldPrefix = 'InServTrans'
    # # proximitySubLayerID = 1  # this is proposed transmission lines
    # # proximityFieldPrefix = 'PropTrans'
    # whereClause = ''
    # whereClause = 'VOLTAGE_KV > 200'
    # # whereClause = 'VOLTAGE_KV > 200 AND VOLTAGE_KV < 140000'  # VOLTAGE_KV field for transmission

    ## substations
    # proximityItemID = '978e2ef30e014722803bedbd126940e9'  # Substations_from_Velocity_Suite
    # proximitySubLayerID = 0  # this is in service subs
    # proximityFieldPrefix = 'InServSubs'
    # proximitySubLayerID = 1  # this is proposed subs
    # proximityFieldPrefix = 'PropSubs'
    # whereClause = 'MX_VOLT_KV > 200'  # MX_VOLT_KV for subs

    # ####    # debug only end  *****************************

    # when a '' string or None is passed to the service whereClause becomes the default published value
    if whereClause == 'noWhereClause':
        whereClause = ''

    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")

    # find the site metric parcels and proximity layers (site_metrics_inputParcels)
    arcpy.AddMessage(f"Getting Geoportal layers")
    t0 = time.time()
    inputParcelsItem = gis.content.get(parcelsItemID)
    inputParcelsLyr = inputParcelsItem.layers[0]
    proximityItem = gis.content.get(proximityItemID)
    proximityLyr = proximityItem.layers[int(proximitySubLayerID)]
    t1 = time.time()
    arcpy.AddMessage(f"...   ... done in  {datetime.timedelta(seconds=t1-t0)}")

    # In case there is a voltage selection
    if whereClause and whereClause != "":
        arcpy.AddMessage('Selecting data')
        try:
            context = {"overwrite": True}
            selected_vector_layer = find_locations.find_existing_locations(input_layers=[proximityLyr, inputParcelsLyr],
                                                                           expressions=[{"operator": "and", "layer": 0,
                                                                                         "spatialRel": "withinDistance",
                                                                                         "selectingLayer": 1,
                                                                                         "distance": 50,
                                                                                         "units": "miles"},
                                                                                        {"operator": "and", "layer": 0,
                                                                                         "where": whereClause}
                                                                                        ],
                                                                           context=context)
            proximityLyr = selected_vector_layer

            # check that vectorLyr has features
            numberOfFeatures = proximityLyr.query(where='1=1', return_count_only=True)
            if numberOfFeatures == 0:
                raise Exception

        except Exception as e:
            print (e)
            # return an empty dataset
            recSet = returnEmptyDataset(proximityFieldPrefix)

            # set the responses
            setResponses(proximityFieldPrefix, recSet)
            sys.exit()

    # DO NOT use context because the proximity features also need to be within the context
    # DO NOT use the extent of the feature layer
    # inputParcelsLyr.properties.extent  # gives a wrong extent
    # inputParcelsLyr.query(return_extent_only=True)

    try:
        nearestItem = find_nearest(analysis_layer=inputParcelsLyr,
                                     near_layer=proximityLyr,
                                     measurement_type="StraightLine",
                                     max_count="1",
                                     search_cutoff=100,
                                     search_cutoff_units="Miles",
                                     output_name=f"sitemetrics_nearest_{proximityFieldPrefix}_DEV")
    except Exception as e:
        try:
            nearestItem = gis.content.search(f"sitemetrics_nearest_{proximityFieldPrefix}_DEV", 'feature layer')[0]  # tmpParcelSolar
            nearestItem.delete()
        except Exception as e:
            textResponse = f"### {proximityFieldPrefix} FAILED ### "
            arcpy.AddMessage(textResponse)
            arcpy.SetParameterAsText(8, str(textResponse))
            sys.exit()
        textResponse = f"### {proximityFieldPrefix} FAILED ### "
        arcpy.AddMessage(textResponse)
        arcpy.SetParameterAsText(8, str(textResponse))
        sys.exit()

    # Get the stats table
    nearestLyr = nearestItem.layers[1]
    nearestSDF = nearestLyr.query(where='1=1', return_geometry=False).sdf

    # delete the nearestItem from geoportal
    nearestItem.delete()

    # Prepare stats table
    nearestSDF = nearestSDF[['from_parcelid', 'to_name', 'total_miles']].copy()
    nearestSDF.rename(columns={'from_parcelid': 'parcelid', 'total_miles': f'{proximityFieldPrefix}_Miles', 'to_name': f'{proximityFieldPrefix}_Name'}, inplace=True)

    # return the stats table as a RecordSet without writing to disk
    final_stats_table = nearestSDF.spatial.to_featureset()
    arcpy.AddMessage('Writing to record set')
    recSet = arcpy.RecordSet()
    recSet.load(final_stats_table)
    # set the responses
    setResponses(proximityFieldPrefix, recSet)

except arcpy.ExecuteError:
    print('-1-')
    print(arcpy.GetMessages(1))
    print('-2-')
    print(arcpy.GetMessages(2))
    arcpy.AddError('-1-')
    arcpy.AddError(arcpy.GetMessages(1))
    arcpy.AddError('-2-')
    arcpy.AddError(arcpy.GetMessages(2))
    arcpy.SetParameterAsText(8, str(arcpy.GetMessages(1) + "  -  " + arcpy.GetMessages(2)))
except Exception as e:
    print(e)
    arcpy.AddError(e)
    arcpy.SetParameterAsText(8, str(e))
