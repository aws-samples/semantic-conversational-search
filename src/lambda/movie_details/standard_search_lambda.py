import json
import boto3
import os
from utils import llm_utils
import time

from opensearchpy import (
    AWSV4SignerAuth
)

#openAPI schema


#handler
def lambda_handler(event, context):

    #retrieving info from the agent's request
    action = event['actionGroup']
    api_path = event['apiPath']

    #get region
    region_name = os.environ.get('AWS_REGION')

    #columns names from the opensearch index
    data_columns = ['tmdb_id', 'original_language', 'original_title', 'description', 'genres', 'year', 'keywords', 'director', 'actors', 'popularity', 'popularity_bins',
                  'vote_average', 'vote_average_bins']

    # Check if "parameters" is present in the event
    if "parameters" not in event or not isinstance(event["parameters"], list):
        raise ValueError("Invalid event format: 'parameters' key not found or not a list.")

    prop_value_list = []

    for parameter in event["parameters"]:
       if parameter['name'] == "properties":
          prop_value_list = json.loads(parameter['value'].replace("'", "\""))

    #retrieve parameters from AWS Secret manager
    secret_value_str = llm_utils.get_secret("semantic-api", region_name)
    secret_value_dict = json.loads(secret_value_str)

    os_host = secret_value_dict['os_host']
    index_name = secret_value_dict['index_name']
    
    #auth object required to connect to opensearch
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

    #connecting to opensearch serverless
    os_client = llm_utils.connect_to_aoss(auth, os_host)

    #querying opensearch
    start_time = time.time()
    response = llm_utils.standard_query_opensearch(prop_value_list, os_client, index_name, data_columns)
    end_time = time.time()
    execution_time = end_time - start_time

    print(f"Querying OpenSearch took {execution_time:.6f} seconds.")

    #formating response to match the agent's expectations
    response_body = {
        'application/json': {
            'body': str(response)
        }
    }

    action_response = {
        'actionGroup': event['actionGroup'],
        'apiPath': event['apiPath'],
        'httpMethod': event['httpMethod'],
        'httpStatusCode': 200,
        'responseBody': response_body
    }

    response = {'response': action_response}

    return response