import pyodbc
import textwrap
import json
import requests
from datetime import datetime

# Multiple facets
# http://localhost:8983/solr/opentech/select?q=faucet&facet=true&facet.field=brand&facet.field=parentCategoryName&facet.limit=10

# Filter by LC 	
# http://localhost:8983/solr/opentech/select?q=steel&fq=availableLCs:11451&facet=true&facet.field=brand&facet.limit=10
# http://localhost:8983/solr/opentech/select?q=*:*&fq=availableLCs:11451&facet=true&facet.field=brand&facet.limit=10
# http://localhost:8983/solr/opentech/select?q=steel&fq=(availableLCs:11451 AND brand:HALEX)&facet=true&facet.field=brand&facet.limit=10

# Category Tree
# http://localhost:8983/solr/opentech/select?q=*:*&facet.pivot=cat_level_0,cat_level_1,cat_level_2&facet=true&facet.field=parentCategoryName&facet.limit=10

class SolrIndexer:

    def __init__(self):
        server = 'LP-IV9\SQLEXPRESS'
        database = 'TEST'
        username = 'sa'
        password = 'test'
        cnxn = pyodbc.connect('DRIVER={ODBC Driver 13 for SQL Server};SERVER=' +
                              server+';DATABASE='+database+';UID='+username+';PWD=' + password)
        self.cnxn = cnxn

    def fetchSKUCount(self):
        try:
            cursor = self.cnxn.cursor()
            countQuery = textwrap.dedent("""
                select count(1) as total_count from TEST_CATALOG.dbo.dcs_sku sku
                inner join TEST_CATALOG.dbo.ws_sku wssku on sku.sku_id=wssku.sku_id
                inner join TEST_CATALOG.dbo.dcs_prd_chldsku skuprd on sku.sku_id=skuprd.sku_id
                inner join TEST_CATALOG.dbo.WS_PRODUCT prd on prd.product_id=skuprd.product_id
                """)
            countRow = cursor.execute(countQuery).fetchone()
            print('countRow - ' + str(countRow.total_count))
            return countRow.total_count
        except pyodbc.DatabaseError as err:
            print(err)

    def fetchAvailableLCs(self, productId):
        cursor = self.cnxn.cursor()
        availableLCQuery = textwrap.dedent("""
                        select skulc.sku_id as sku_id, skulc.available_lc as available_lc from TEST_CATALOG.dbo.WS_SKU_LC skulc
	                    inner join TEST_CATALOG.dbo.dcs_prd_chldsku skuprd on skulc.sku_id=skuprd.sku_id
	                    WHERE skuprd.product_id=? ORDER BY skulc.sku_id
                    """)
        cursor.execute(availableLCQuery, productId)
        availableLCRows = cursor.fetchall()
        return availableLCRows

    def fetchDynamicAttrs(self, productId):
        cursor = self.cnxn.cursor()
        dynamicAttrsQuery = textwrap.dedent("""
                        select skudynattr.sku_id as sku_id, skudynattr.ws_dynamic_attributes as ws_dynamic_attributes from TEST_CATALOG.dbo.WS_SKU_DYNAMIC_ATTR skudynattr
                        inner join TEST_CATALOG.dbo.dcs_prd_chldsku skuprd on skudynattr.sku_id=skuprd.sku_id
                        WHERE skuprd.product_id=? ORDER BY skudynattr.sku_id
                    """)
        cursor.execute(dynamicAttrsQuery, productId)
        dynamicAttrsRows = cursor.fetchall()
        return dynamicAttrsRows

    def fetchCategoryData(self, productId):
        cursor = self.cnxn.cursor()
        categoryDataQuery = textwrap.dedent("""
                        select cat.category_id as category_id,cat.display_name as cat_name, wscat.large_image_url as cat_img from TEST_CATALOG.dbo.dcs_prd_anc_cats catprd
                        inner join TEST_CATALOG.dbo.dcs_category cat on cat.category_id=catprd.category_id
                        inner join TEST_CATALOG.dbo.WS_CATEGORY wscat on wscat.id=catprd.category_id
                        WHERE catprd.product_id=? ORDER BY catprd.sequence_num
                    """)
        cursor.execute(categoryDataQuery, productId)
        categoryDataRows = cursor.fetchall()
        return categoryDataRows

    def processRecords(self, count):
        cursor = self.cnxn.cursor()
        totalCount = count
        counter = 0
        try:
            while counter < totalCount:
                baseQuery = textwrap.dedent("""
                select prd.product_id as product_id, prd.product_type as product_type, sku.sku_id as sku_id,
                sku.display_name as display_name, wssku.wise_item_num as erp_item_number, wssku.catalog_number as catalog_number,
                wssku.item_popularity as item_popularity,wssku.large_image_url as large_image_url, wssku.brand as brand, wssku.marke_desc as marketing_desc
                from TEST_CATALOG.dbo.dcs_sku sku
                inner join TEST_CATALOG.dbo.ws_sku wssku on sku.sku_id=wssku.sku_id
                inner join TEST_CATALOG.dbo.dcs_prd_chldsku skuprd on sku.sku_id=skuprd.sku_id
                inner join TEST_CATALOG.dbo.WS_PRODUCT prd on prd.product_id=skuprd.product_id
                ORDER BY prd.product_id OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
                """)
                cursor.execute(baseQuery, counter, 1000)
                rows = cursor.fetchall()
                skuDocArray = []
                lastProductId = None
                availableLCRows = None
                dynamicAttrsRows = None
                categoryDataRows = None
                
                for row in rows:
                    productId = row.product_id
                    skuId = row.sku_id
                    itemPopularity = 99999
                    if row.item_popularity != None:
                        itemPopularity = int(row.item_popularity)

                    skuDoc = {
                        'id': skuId,
                        'productId': productId,
                        'erpItemNum': row.erp_item_number,
                        'displayName': row.display_name,
                        'brand': row.brand,
                        'productType': row.product_type,
                        'itemPopularity': itemPopularity,
                        'largeImageURL': row.large_image_url,
                        'marketingDescription': row.marketing_desc
                    }
                    if lastProductId is None or lastProductId != productId:
                        availableLCRows = self.fetchAvailableLCs(productId)
                        dynamicAttrsRows = self.fetchDynamicAttrs(productId)
                        categoryDataRows = self.fetchCategoryData(productId)

                    if len(availableLCRows) > 0:
                        availableLCs = []
                        for availableLCRow in availableLCRows:
                            if availableLCRow.sku_id == skuId:
                                availableLCs.append(availableLCRow.available_lc)

                        skuDoc['availableLCs'] = availableLCs

                    if len(dynamicAttrsRows) > 0:
                        for dynamicAttrsRow in dynamicAttrsRows:
                            if dynamicAttrsRow.sku_id == skuId:
                                attribute = dynamicAttrsRow.ws_dynamic_attributes
                                attribute = attribute.split('|')
                                key = 'attr_' + attribute[0]
                                skuDoc[key] = attribute[1]

                    categoryDataRowsCount = len(categoryDataRows)
                    for i in range(categoryDataRowsCount):
                        key = 'cat_level_' + str(i)
                        skuDoc[key] = categoryDataRows[i].cat_name
                        if i == (categoryDataRowsCount - 1):
                            skuDoc['parentCategoryName'] = categoryDataRows[i].cat_name

                    lastProductId = productId
                    skuDocArray.append(skuDoc)

                # print(json.dumps(skuDocArray))
                url = 'http://localhost:8983/solr/opentech/update?commit=true'
                headers = {
                    'Content-Type': 'application/json'
                }
                response = requests.post(url, headers=headers, data=json.dumps(skuDocArray))
                print(response.status_code)
                counter += 1000
        except pyodbc.DatabaseError as err:
            print(err)


solrIndexer = SolrIndexer()
print('start time -  ' + str(datetime.now()))
totalSKUCount = solrIndexer.fetchSKUCount()
solrIndexer.processRecords(totalSKUCount)
print('end time -  ' + str(datetime.now()))
