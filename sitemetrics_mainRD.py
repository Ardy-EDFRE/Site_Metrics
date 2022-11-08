import os
import arcpy
from collections import namedtuple
from arcgis.gis import GIS
from arcgis.features import FeatureSet, GeoAccessor, GeoSeriesAccessor
from arcgis.geometry import Geometry
from arcgis.geometry.filters import intersects
from arcgis.features.manage_data import overlay_layers
from arcgis.features import find_locations
from arcgis.geometry import filters
import pandas as pd
import json
import time
from uuid import uuid4


def mapParcelIDandRunIDFields(inParcels, inParcelsIDField):
    runID = str(uuid4())

    inParcelsJson = inParcels.JSON
    inParcelsJson = inParcelsJson.replace(inParcelsIDField, 'parcelid')
    inParcelsDict = json.loads(inParcelsJson)

    newFieldsList = [f for f in inParcelsDict['fields'] if 'parcelid' not in f['name']]
    parcelIDField = {
        "name": "parcelid",
        "type": "esriFieldTypeString",
        "alias": "parcelid",
        "length": 255
    }
    runIDField = {
        "name": "runid",
        "type": "esriFieldTypeString",
        "alias": "runid",
        "length": 255
    }
    newFieldsList.append(parcelIDField)
    newFieldsList.append(runIDField)
    inParcelsDict['fields'] = newFieldsList

    # add the runID value to all the features
    for f in inParcelsDict['features']:
        f['attributes']['runid'] = runID

    inParcels_api_fset = FeatureSet.from_dict(inParcelsDict)

    return inParcels_api_fset


def uploadFeaturesToGeoportalLyr(inParcels, inputParcelsLyr, idFieldName):
    # push the parcels to the parcels layer in geoportal
    inParcels_api_fset = mapParcelIDandRunIDFields(inParcels, idFieldName)
    # inParcels.save(r"G:\Users\JoseLuis\arcgis_scripts_enxco\site_metrics", "test.shp")

    inputParcelsLyr.delete_features(where="1=1")
    # When making large number (250+ records at once) of edits,
    # append should be used over edit_features to improve performance and ensure service stability.
    inputParcelsLyr.edit_features(adds=inParcels_api_fset)

    return inputParcelsLyr


def createInAndOutBuildableField(unionFLyr):
    union_fset = unionFLyr.query()
    union_features = union_fset.features

    fid_job_column = [col for col in union_features[0].fields if 'fid_j' in col][0]

    for fd in union_features:
        if fd.attributes[fid_job_column] < 1:
            fd.attributes['parcel_bld_id'] = fd.attributes['parcelid'] + '_0'
        else:
            fd.attributes['parcel_bld_id'] = fd.attributes['parcelid'] + '_1'

    unionFLyr.edit_features(updates=union_features)

    return unionFLyr


try:
    inParcels = arcpy.GetParameter(0)
    idFieldNameParcels = arcpy.GetParameterAsText(1)

    # debug only  *****************************
    # inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_polys_nozm"
    inParcels = r"G:\Users\Ardy\GIS\APRX\scratch.gdb\test_parcels_FEMA"
    idFieldNameParcels = 'parcelid'
    # inParcels = r"G:\Projects\USA_West\Flores\05_GIS\053_Data\Parcels_Flores_CoreLogic_ToLoad_LPM_20221024.shp"
    # idFieldNameParcels = 'FID'
    # debug only end  *****************************

    idFieldNameBldParcels = 'parcel_bld_id'

    # the BL_Source is always the Solar national

    # Buildable Land # FEMA 100 Year Floodplain  # 500 Year Floodplain
    # BL_Source      # F100_Acres                # F500_Acres
    # BL_Acres       # F100_Pcnt                 # F500_Pcnt
    # BL_Pcnt        # F100_BL_Acres             # F500_BL_Acres
                     # F100_BL_Pcnt              # F500_BL_Pcnt

    # Slope(raster)      # Forested Land(raster)  # Bedrock - Shallow   # Bedrock - MidDepth(101 to 300 cm)
    # Slp10_Acres        # Forest_Acres           # BdRckSh_Acres       # BdRckMD_Acres
    # Slp10_Pcnt         # Forest_Pcnt            # BdRckSh_Pcnt        # BdRckMD_Pcnt
    # Slp10_BL_Acres     # Forest_BL_Acres        # BdRckSh_BL_Acres    # BdRckMD_BL_Acres
    # Slp10_BL_Pcnt      # Forest_BL_Pcnt         # BdRckSh_BL_Pcnt     # BdRckMD_BL_Pcnt

    raster_inputs = {
        "Forests_Only_From_LANDFIRE":  "Forest",
        'Slope_over10perc_ned2usa_60m': "Slp10"
    }
    vectorParams = namedtuple("vectorParams", "vectorItemName field whereClause")
    vector_inputs = {
        "FEMA100": vectorParams("FEMA Flood Hazard Areas", 'F100', "FLD_ZONE in ('A', 'A99', 'AE', 'AH', 'AO')"),
        "FEMA500": vectorParams("FEMA Flood Hazard Areas", 'F500', "FLD_ZONE in ('X')")
    }

    # raster_service_inputs = ['Forests_Only_From_LANDFIRE', 'Slope_over10perc_ned2usa_60m']
    # vector_service_inputs = ['1a58e6becd2d4ba4bb8c401997bebe29']

    inParcels = arcpy.FeatureSet(inParcels)

    # converting the inParcels featureset to a spatial dataframe. We will join the stats to parcelsSDF
    arcpy.CopyFeatures_management(inParcels, 'memory/tmp1')
    parcelsSDF = pd.DataFrame.spatial.from_featureclass('memory/tmp1')
    arcpy.Delete_management('memory/tmp1')

    if type(parcelsSDF[idFieldNameParcels]) == 'Str':
        parcelsSDF[idFieldNameParcels] = parcelsSDF[idFieldNameParcels].astype('int')

    parcelsBuildableUnionLayerName = "sitemetrics_parcels_buildable_union"

    # the stats for each parcel are for the total of the parcel and for the buildable part of the parcel
    # prepare the input parcels and intersect with the buildable land
    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")

    # find the solar national buildable land layer
    buildableItem = gis.content.get('21d180c3e40847a69c32cec4166fbeca')
    buildableLyr = buildableItem.layers[0]

    # find the site metric parcels layer
    inputParcelsItem = gis.content.search('site_metrics_inputParcels', 'feature layer')[0]
    inputParcelsLyr = inputParcelsItem.layers[0]

    inParcelsDesc = arcpy.Describe(inParcels)
    inParcelsExtent = inParcelsDesc.extent
    # creating context object and send to image server
    context = {"extent": {"xmin": inParcelsExtent.XMin,
                          "ymin": inParcelsExtent.YMin,
                          "xmax": inParcelsExtent.XMax,
                          "ymax": inParcelsExtent.YMax,
                          "spatialReference": {"wkid": inParcelsDesc.spatialReference.factoryCode}},
               "overwrite": True
               }

    # Intersect buildable and parcels in geoportal
    inputParcelsLyr.delete_features(where="1 = 1")

    inputParcelsLyr = uploadFeaturesToGeoportalLyr(inParcels, inputParcelsLyr, idFieldNameParcels)

    # intersecting buildable lands polys into a (new or preexisting) geoportal layer
    # https://developers.arcgis.com/python/api-reference/arcgis.features.find_locations.html
    try:
        parcel_bld_item = gis.content.search('tmpParcelSolar', 'feature layer')[0]
        parcel_bld_item.delete()
    except Exception as e:
        print('tmpParcelSolar does not exist yet...')

    arcpy.AddMessage("Uploading parcels")
    # 00:00:58.45 seconds - intersect find_locations
    # find_locations - derive_new_locations returns partial feature records vs find_existing_locations was returning a much larger area
    # selected_buildable_layer = find_locations.derive_new_locations(input_layers=[buildableLyr, inputParcelsLyr],
    #                                                                expressions=[{"operator": "and", "layer": 0,
    #                                                                              "spatialRel": "intersects",
    #                                                                              "selectingLayer": 1}],
    #                                                                output_name='tmpParcelSolar', context=context)

    # 00:00:58.528 - withinDistance 0.1 feet find_locations
    selected_buildable_layer = find_locations.derive_new_locations(input_layers=[buildableLyr, inputParcelsLyr],
                                                                   expressions=[{"operator": "and",
                                                                                 "layer": 0,
                                                                                 "spatialRel": "withinDistance",
                                                                                 "selectingLayer": 1,
                                                                                 "distance": 0.001,
                                                                                 "units": "feet"}],
                                                                   output_name='tmpParcelSolar', context=context)

    # gis.content.search is for name specific & gis.content.get is for item id specific
    try:
        parcels_item = gis.content.search('sitemetrics_parcels_buildable_union')[0]
        parcels_item.delete()
    except Exception as e:
        print('sitemetrics_parcels_buildable_union does not exist yet')

    arcpy.AddMessage("Unionising parcels with solar national buildable land")
    unionItem = overlay_layers(inputParcelsLyr, selected_buildable_layer, overlay_type='Union',
                               output_name=parcelsBuildableUnionLayerName, context=context)

    unionFLyr = unionItem.layers[0]

    # remove any parcels outside of union EXAMPLE: "parcelid = -1"
    unionFLyr.delete_features(where="parcelid = ''")

    # modify parcelid If fid_feature_set  is -1 then parcelid = parcelid_0 otherwise parcelid  = parcelid_1)
    # add new parcelid field for identifying within buildable (parcel_bld_id)
    parcel_bld_def = {'name': 'parcel_bld_id',
                      'type': 'esriFieldTypeString',
                      'alias': 'parcel_bld_id',
                      'domain': None,
                      'editable': True,
                      'nullable': True,
                      'sqlType': 'sqlTypeVarchar',
                      'length': 255}

    unionFLyr.manager.add_to_definition({'fields': [parcel_bld_def]})

    unionFLyr = createInAndOutBuildableField(unionFLyr)

    # get the current run ids. do we really need this?
    tmp_parcel_df = unionFLyr.query().sdf
    tmp_run_id = tmp_parcel_df['runid'][0]

    df_list = []
    # summarize area by parcelid and then by parcel_bld_id
    parcelBuildableAcres = tmp_parcel_df.groupby([idFieldNameParcels]).analysisarea.sum()
    parcelBuildableAcres = parcelBuildableAcres.to_frame()
    # df_list.append(parcelBuildableAcres)

    # summarize area by parcelsBuildableUnionIDField
    summarize_df = tmp_parcel_df.groupby([idFieldNameParcels, idFieldNameBldParcels]).analysisarea.sum().reset_index()

    # pivot table to convert parcelsBuildableUnionIDField to parcelid
    summarize_df['buildableIndex'] = summarize_df[idFieldNameBldParcels].str[-1:]
    tmp_pivot_table = summarize_df.pivot_table(index=idFieldNameParcels, columns='buildableIndex',
                                               values='analysisarea')
    tmp_pivot_table.reset_index(inplace=True)
    tmp_pivot_table.rename(
        columns={'0': 'outBldAcres',
                 '1': 'inBldAcres'},
        inplace=True)
    df_list.append(tmp_pivot_table)

    # Make gp service calls asynchronously
    rasterToolbox = 'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercRaster;token={};{}'.format(
        gis._con.token, gis.url)
    vectorToolbox = 'https://geoportal.edf-re.com/raggp/services;Other/getAcresAndPercVector;token={};{}'.format(
        gis._con.token, gis.url)
    arcpy.ImportToolbox(rasterToolbox)
    arcpy.ImportToolbox(vectorToolbox)

    arcpy.AddMessage("Making Raster Calls")
    resultList = []
    # Make raster calls
    for tmp_raster in raster_inputs:
        tmpFieldPrefix = raster_inputs[tmp_raster]
        tmp_raster_result = arcpy.getAcresAndPercRaster.getAcresAndPercRaster(parcelsBuildableUnionLayerName,
                                                                              tmp_run_id,
                                                                              idFieldNameParcels, idFieldNameBldParcels,
                                                                              'Area in Square Miles',
                                                                              tmp_raster, tmpFieldPrefix)
        resultList.append(tmp_raster_result)

    arcpy.AddMessage("Making Vector Calls")
    # Make vector calls
    for tmp_vector in vector_inputs:
        tmpVectorItem = vector_inputs[tmp_vector]
        tmp_vector_result = arcpy.getAcresAndPercVector.getAcresAndPercVector(parcelsBuildableUnionLayerName,
                                                                              tmp_run_id,
                                                                              idFieldNameParcels, idFieldNameBldParcels,
                                                                              tmpVectorItem.vectorItemName, tmpVectorItem.field, tmpVectorItem.whereClause)
        resultList.append(tmp_vector_result)

    # Wait for all the calls to be processed
    waitTimeStart = time.time()
    for tmp_result in resultList:
        while tmp_result.status < 4:
            time.sleep(0.2)
            waitTime = time.time() - waitTimeStart
            if waitTime > 120:
                arcpy.AddMessage(f"Error: map service not responding. {tmp_result}")
                sys.exit()

    # This is added to get the resultOutputs from our gp results list to a record set
    arcpy.AddMessage("Cleaning up final table")

    # store all the results in a list with dataframes
    for result in resultList:
        d = json.loads(result.getOutput(0).JSON)  # response from gp calls as JSON
        df = pd.json_normalize(d, record_path=['features'])  # dataframe created from JSON
        df_list.append(df)

    # join all the tables at once because they are in a list
    # fix concat to join function
    final_stats_table_merge = pd.concat(df_list, axis=1)
    final_stats_table_merge.reset_index(inplace=True)
    final_stats_table_merge.columns = final_stats_table_merge.columns.str.replace('attributes.',
                                                                                  '')  # JSON is converted but has attributes.something when creating columns in dataframe
    final_stats_table_merge = final_stats_table_merge.T.drop_duplicates().T  # Dropping duplicate OBJECTID & ParcelID columns

    # join the final statists table with the input parcels
    final_stats_table_merge = final_stats_table_merge.join(parcelBuildableAcres, on=idFieldNameParcels)
    final_stats_table_merge[idFieldNameParcels] = final_stats_table_merge[idFieldNameParcels].astype('int')
    parcelsWithStatsSDF = parcelsSDF.merge(final_stats_table_merge, left_on=idFieldNameParcels,
                                           right_on=idFieldNameParcels)

    # return the statistics recordset
    arcpy.AddMessage("Creating final record set")
    inParcelsWithStats_arcpyfset = arcpy.FeatureSet()
    inParcelsWithStats_arcgisfset = parcelsWithStatsSDF.spatial.to_featureset()
    inParcelsWithStats_arcpyfset.load(inParcelsWithStats_arcgisfset)
    arcpy.SetParameter(2, inParcelsWithStats_arcpyfset)

    # elapsed_time = time.time() - tool_run_time
    # timeString = time.strftime('%H:%M:%S' + str(round(elapsed_time % 1, 3))[1:], time.gmtime(elapsed_time))
    # arcpy.AddMessage(timeString)

    arcpy.AddMessage("Success")

except arcpy.ExecuteError:
    print('-1-')
    print(arcpy.GetMessages(1))
    print('-2-')
    print(arcpy.GetMessages(2))
    arcpy.AddError('-1-')
    arcpy.AddError(arcpy.GetMessages(1))
    arcpy.AddError('-2-')
    arcpy.AddError(arcpy.GetMessages(2))
except Exception as e:
    print(e)
    arcpy.AddError(e)
