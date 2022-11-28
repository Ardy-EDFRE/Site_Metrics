import sys, os, arcpy
from arcgis.gis import GIS
from arcgis.features import GeoAccessor, GeoSeriesAccessor, FeatureSet
from arcgis.raster.analytics import zonal_statistics_as_table
import pandas as pd
import json
try:
    parcelsBuildableUnionItemName = arcpy.GetParameterAsText(0)
    runid = arcpy.GetParameterAsText(1)
    parcelsIDField = arcpy.GetParameterAsText(2)
    parcelsBuildableUnionIDField = arcpy.GetParameterAsText(3)
    inParcelsAreaField = arcpy.GetParameterAsText(4)
    reclass01RasterItemName = arcpy.GetParameterAsText(5)
    reclass01RasterFieldPrefix = arcpy.GetParameterAsText(6)
    # # # ###    # debug only  *****************************
    # parcelsBuildableUnionItemName = 'sitemetrics_parcels_buildable_union'
    # runid = 'cb42ef9d-0324-4547-8580-3a23c1315182'
    # parcelsIDField = 'parcelid'
    # parcelsBuildableUnionIDField = 'parcel_bld_id'
    # inParcelsAreaField = 'Area in Square Miles'
    # reclass01RasterItemName = 'Forests_Only_From_LANDFIRE'
    # reclass01RasterFieldPrefix = 'Forest'
    # # # ####    # debug only end  *****************************
    # generalTimer = Timer()
    # generalTimer.start()
    gis = GIS("https:??geoportal.edf-re.com?portal".replace(':??', '://').replace('?', '/'),
              "Geoportalcreator", "secret1creator**")
    # find the zone layer
    zoneItem = gis.content.search(parcelsBuildableUnionItemName, 'feature layer')[0]
    zoneFLyr = zoneItem.layers[0]
    # find the raster layer
    rasterItem = gis.content.get(reclass01RasterItemName)
    rasterLyr = rasterItem.layers[0]
    # stats
    zonal_stats_item = zonal_statistics_as_table(input_zone_raster_or_features=zoneFLyr,
                                                 input_value_raster=rasterLyr,
                                                 zone_field=parcelsBuildableUnionIDField,
                                                 statistic_type="MEAN",
                                                 gis=gis)  # output_name
    tableLyr = zonal_stats_item.tables[0]
    table_sdf = tableLyr.query().sdf
    # areas per parcel  (acres = sq miles * 640)
    zone_sdf = zoneFLyr.query().sdf
    parcelAreasDF = zone_sdf.groupby([parcelsIDField]).analysisarea.sum().reset_index()
    parcelAreasDF[f'Parcel_Acres'] = parcelAreasDF['analysisarea'].multiply(640)
    parcelAreasDF.drop(columns=['analysisarea'], inplace=True)
    # areas of buildable per parcel
    parcelBLAreasDF = zone_sdf[zone_sdf[parcelsBuildableUnionIDField].str.endswith('_1')].groupby([parcelsIDField]).analysisarea.sum().reset_index()
    parcelBLAreasDF[f'BL_Acres'] = parcelBLAreasDF['analysisarea'].multiply(640)
    parcelBLAreasDF.drop(columns=['analysisarea'], inplace=True)
    parcelAreasDF = pd.merge(parcelAreasDF, parcelBLAreasDF, on=parcelsIDField, how='left')
    # calculate the acres based on the mean value of the stats * the analysis area from the zone_sdf
    joinedDF = pd.merge(zone_sdf, table_sdf, on=parcelsBuildableUnionIDField, how='left')
    joinedDF['buildAcres'] = joinedDF['analysisarea'] * joinedDF['mean']
    # summarize area by parcelsBuildableUnionIDField
    summarize_df = joinedDF.groupby([parcelsIDField, parcelsBuildableUnionIDField]).buildAcres.sum().reset_index()
    # pivot table to convert parcelsBuildableUnionIDField to parcelid
    summarize_df['buildableIndex'] = summarize_df[parcelsBuildableUnionIDField].str[-1:]
    tmp_pivot_table = summarize_df.pivot_table(index=parcelsIDField, columns='buildableIndex', values='buildAcres')
    tmp_pivot_table.reset_index(inplace=True)
    # total acres (acres = sq miles * 640)
    tmp_pivot_table[f'{reclass01RasterFieldPrefix}_Acres'] = (tmp_pivot_table['0'] + tmp_pivot_table['1']).multiply(640)
    # forest acres in buildable
    tmp_pivot_table[f'{reclass01RasterFieldPrefix}_BL_Acres'] = tmp_pivot_table['1'].multiply(640)
    # fix fields
    tmp_pivot_table.drop(columns=['0', '1'], inplace=True)
    # bring in the total parcel area
    tmp_pivot_table = pd.merge(tmp_pivot_table, parcelAreasDF, on=parcelsIDField, how='left')
    # calculate percentages
    tmp_pivot_table[f'{reclass01RasterFieldPrefix}_Pcnt'] = tmp_pivot_table[f'{reclass01RasterFieldPrefix}_Acres'] / tmp_pivot_table['Parcel_Acres'] * 100.0
    tmp_pivot_table[f'{reclass01RasterFieldPrefix}_BL_Pcnt'] = tmp_pivot_table[f'{reclass01RasterFieldPrefix}_BL_Acres'] / tmp_pivot_table['BL_Acres'] * 100.0
    # drop redundant fields that are already inthe main program
    tmp_pivot_table.drop(columns=['Parcel_Acres', 'BL_Acres'], inplace=True)
    tmp_pivot_table.fillna(0, inplace=True)
    zonal_stats_item.delete()
    # return the stats table as a RecordSet without writing to disk
    final_stats_table = tmp_pivot_table.spatial.to_featureset()
    arcpy.AddMessage('Writing to record set')
    recSet = arcpy.RecordSet()
    recSet.load(final_stats_table)
    # set the responses
    arcpy.SetParameter(7, recSet)
    # elapsed_time = generalTimer.stop()
    # timeString = time.strftime('%H:%M:%S' + str(round(elapsed_time % 1, 3))[1:], time.gmtime(elapsed_time))
    textResponse = f"### {reclass01RasterFieldPrefix} COMPLETED SUCCESSFULLY BECAUSE I ROCK ###"
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
    arcpy.SetParameterAsText(6, str(arcpy.GetMessages(1) + "  -  " + arcpy.GetMessages(2)))
except Exception as e:
    print(e)
    arcpy.AddError(e)
    arcpy.SetParameterAsText(6, str(e))
