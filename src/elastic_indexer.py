import json
import requests
from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk


class ElasticIndexer():

    def __init__(self):
        pass

    def processJSONFile(self, filePath):
        file = open(filePath, 'r')
        try:
            jsonObj = json.loads(file.read())
        except:
            print('json.loads() failed')
        finally:
            file.close()
        return jsonObj

    def locationsByPimId(self):
        locationDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\location_data.json'
        locationDataJSONObj = self.processJSONFile(locationDataFile)

        skuDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\sku_data.json'
        skuDataJSONObj = self.processJSONFile(skuDataFile)
        skuArray = skuDataJSONObj['pim_skus']

        for locationObj in locationDataJSONObj:
            pimId = locationObj['PIM_ID']
            for sku in skuArray:
                skuId = sku['sku']['primaryAttributes']['idSku']
                if skuId == pimId:
                    print(pimId, locationObj['COMPANY_NUMBER'])
                    break

    def locationsByItemNum(self):
        locationDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\data\location_data.json'
        locationDataJSONObj = self.processJSONFile(locationDataFile)

        locationItemsDict = {}

        for locationObj in locationDataJSONObj:
            itemNumber = locationObj['ITEM_NUMBER']
            if itemNumber in locationItemsDict:
                locationItems = locationItemsDict[itemNumber]
                locationItems.append(locationObj)
            else:
                locationItems = [locationObj]
                locationItemsDict[itemNumber] = locationItems

        return locationItemsDict

    def categoryById(self):
        categoryDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\data\category_data.json'
        categoryDataJSONObj = self.processJSONFile(categoryDataFile)

        categoryDict = {}

        for categoryObj in categoryDataJSONObj['pim_categories']['category']:
            categoryId = categoryObj['idcategory']
            categoryDict[categoryId] = categoryObj

        return categoryDict

    def productById(self):
        productDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\data\product_data.json'
        productDataJSONObj = self.processJSONFile(productDataFile)

        productDict = {}

        for productObj in productDataJSONObj['pim_products']:
            productId = productObj['product']['idproduct']
            productDict[productId] = productObj['product']

        return productDict

    def createCategoryHierarchy(self, categoryId, categoryDict):
        categoryHierarchyDict = {}
        if categoryId in categoryDict:
            categoryHierarchy = []
            categoryObj = categoryDict[categoryId]
            idcategoryStr = str(categoryObj['idcategory'])
            while idcategoryStr != 'ECOM_TAXO_root':
                categoryHierarchy.append(categoryObj)
                idcategoryStr = str(categoryObj['idparentcategory'])
                categoryObj = categoryDict[idcategoryStr]

            categoryHierarchy.reverse()

            for i in range(len(categoryHierarchy)):
                categoryHierarchyDict[str(i) +
                                      '.id'] = int(categoryHierarchy[i]['idcategory'])
                categoryHierarchyDict[str(i) +
                                      '.name'] = categoryHierarchy[i]['categoryname']
                categoryHierarchyDict[str(i) +
                                      '.keyword'] = categoryHierarchy[i]['keywords']

        return categoryHierarchyDict

    def buildDocument(self):
        masterLocationItemsDict = self.locationsByItemNum()
        categoryDict = self.categoryById()
        productDict = self.productById()

        skuDataFile = 'D:\AD\Project\opentech\search\Elasticsearch\data\sku_data.json'
        skuDataJSONObj = self.processJSONFile(skuDataFile)

        elastic_doc_list = []

        for skuObj in skuDataJSONObj['pim_skus']:
            elastic_doc = {}
            master_attr = {}
            primaryAttributes = skuObj['sku']['primaryAttributes']
            standardAttributes = skuObj['sku']['standardAttributes']
            searchButNoDisplayAttr = skuObj['sku']['SearchButNoDisplay']

            itemNumber = standardAttributes['idwin']
            productId = primaryAttributes['idproduct']

            if productId in productDict and 'productType' in productDict[productId] and 'categories' in productDict[productId]:
                productObj = productDict[productId]
                if len(primaryAttributes['bulletDescription']) > 0:
                    features = []
                    for bulletDesc in primaryAttributes['bulletDescription']:
                        features.append(bulletDesc['bullet'].strip())
                    master_attr['bullet_description'] = features

                master_attr['sku_id'] = primaryAttributes['idSku']
                master_attr['sku_id'] = primaryAttributes['idSku']
                master_attr['product_id'] = productId
                master_attr['item_number'] = itemNumber
                if 'CatalogNumber' in standardAttributes:
                    master_attr['catalog_number'] = standardAttributes['CatalogNumber']
                master_attr['brand'] = primaryAttributes['brand']
                itemName = primaryAttributes['itemName']
                master_attr['item_name'] = itemName
                master_attr['marketing_description'] = primaryAttributes['MarketingDescription']

                if 'ItemPopularity' in searchButNoDisplayAttr and searchButNoDisplayAttr['ItemPopularity'] != '':
                    master_attr['item_popularity'] = int(
                        searchButNoDisplayAttr['ItemPopularity'])

                if 'wise_avg_price' in searchButNoDisplayAttr and searchButNoDisplayAttr['wise_avg_price'] != '':
                    master_attr['wise_avg_price'] = float(
                        searchButNoDisplayAttr['wise_avg_price'])

                if 'LC2sku' in searchButNoDisplayAttr and searchButNoDisplayAttr['LC2sku'] != '':
                    availableLCs = searchButNoDisplayAttr['LC2sku'].split(';')
                    master_attr['available_lcs'] = availableLCs

                if 'images' in skuObj['sku']:
                    images = []
                    if 'img_large' in skuObj['sku']['images']:
                        images.append(skuObj['sku']['images']['img_large'])
                    if 'img_medium' in skuObj['sku']['images']:
                        images.append(skuObj['sku']['images']['img_medium'])
                    if 'img_small' in skuObj['sku']['images']:
                        images.append(skuObj['sku']['images']['img_small'])
                    master_attr['images'] = images

                if 'dynamicAttributes' in skuObj['sku']:
                    dynamicAttributesDict = {}
                    dynamicAttributes = skuObj['sku']['dynamicAttributes']
                    for dynamicAttribute in dynamicAttributes:
                        dynamicAttributesDict[dynamicAttribute['name']
                                              ] = dynamicAttribute['value']
                        # uom
                    master_attr['dynamic_attrs'] = dynamicAttributesDict

                if 'productType' in productObj:
                    master_attr['product_type'] = productObj['productType']
                else:
                    print(productId)

                categoryId = productObj['categories'][0]['structureGroupNode']
                categoryHierarchyDict = self.createCategoryHierarchy(
                    categoryId, categoryDict)
                master_attr['category'] = categoryHierarchyDict

                parentCategoryDict = {}
                parentCategoryObj = categoryDict[categoryId]
                parentCategoryDict['id'] = categoryId
                parentCategoryDict['name'] = parentCategoryObj['categoryname']
                parentCategoryDict['keywords'] = parentCategoryObj['keywords']

                master_attr['parentCategory'] = parentCategoryDict

                elastic_doc['master'] = master_attr

                if itemNumber in masterLocationItemsDict:
                    locationItemsDict = {}

                    locationItems = masterLocationItemsDict[itemNumber]
                    for locationItem in locationItems:
                        locationId = locationItem['COMPANY_NUMBER']

                        locationItemsDict[locationId +
                                          '.mfg_code'] = locationItem['MFG_CODE']
                        locationItemsDict[locationId +
                                          '.product_group'] = locationItem['PRDUCT_GROUP']
                        locationItemsDict[locationId +
                                          '.vendor_code'] = locationItem['VENDOR_CODE']
                        if locationItem['B2B'] != 'null':
                            locationItemsDict[locationId +
                                              '.b2b'] = locationItem['B2B']
                        if locationItem['B2C'] != 'null':
                            locationItemsDict[locationId +
                                              '.b2c'] = locationItem['B2C']
                        # if locationItem['ALT_ITEM_NAME'] != 'null':
                        #     locationItemsDict[locationId +
                        #                       '.alt_item_name'] = locationItem['ALT_ITEM_NAME']
                        locationItemsDict[locationId +
                                          '.alt_item_name'] = itemName

                    elastic_doc['location'] = locationItemsDict
                
                # elastic_doc_list.append(elastic_doc)
                elastic_doc_list.append(
                    {
                        "_index": "opentech",
                        "_type": "_doc",
                        "_id": itemNumber,
                        '_source': elastic_doc
                    }
                )
                #return elastic_doc_list
        print('Total docs - ' + str(len(elastic_doc_list)))        
        return elastic_doc_list
        # try:
        #     jsonFile = open(
        #         "D:\AD\Project\opentech\search\Elasticsearch\data\elastic_doc.json", "w")
        #     jsonFile.write(json.dumps(elastic_doc_list))
        # except:
        #     print('json.loads() failed')
        # finally:
        #     jsonFile.close()


elasticIndexer = ElasticIndexer()
# elasticIndexer.buildDocument()

es = Elasticsearch('localhost:9200')
elastic_doc_list = elasticIndexer.buildDocument()
bulk(es, elastic_doc_list, request_timeout=120)
