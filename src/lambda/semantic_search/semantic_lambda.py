import json
import boto3
import os
from utils import llm_utils
import time

from opensearchpy import (
    AWSV4SignerAuth
)

#openAPI schema
"""{
  "openapi": "3.0.0",
  "info": {
    "title": "Semantic Search API",
    "version": "1.0.0"
  },
  "paths": {
    "/semantic-search": {
      "get": {
        "description": "Perform semantic search with question as in input and order the response by either popularity, year or ratings",
        "parameters": [
          {
            "name": "question",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "The question asked by the user"
          },
          {
            "name": "orderby",
            "in": "query",
            "required": true,
            "schema": {
              "type": "string"
            },
            "description": "the property to use to sort the response. values can be either popularity, year or ratings. Default value is popularity"
          }
        ],
        "responses": {
          "200": {
            "description": "Successful response",
            "content": {
              "application/json": {
                "schema": {
                  "type": "object",
                  "properties": {
                    "message": {
                      "type": "string"
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

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

    question = "popular movies" #setting a default value
    orderby = "popularity"  #setting a default value

    for parameter in event["parameters"]:
       if parameter['name'] == "orderby":
          orderby = parameter['value']
       if parameter['name'] == "question":
          question = parameter['value']
    
    print(f"question:{question}, orderby:{orderby}")

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
    os_response = llm_utils.query_opensearch(question, os_client, index_name, data_columns, embedding_model="cohere", k=10)
    end_time = time.time()
    execution_time = end_time - start_time

    print(f"Querying OpenSearch took {execution_time:.6f} seconds.")

    #extract object from os response
    response = llm_utils.extract_response_from_os_response(os_response)

    #print(f"response before the sort:{response}")
    #reordering of the response
    if orderby in ['year', 'rating', 'ratings', 'popularity', 'vote_average']:   
      #replacing ratings in case the model passes it instead of vote_average
      if orderby in ['rating', 'ratings']:
         orderby = "vote_average"
      
      #sorting by descending order by default
      response = sorted(response, key=lambda x: float(x[orderby]), reverse=True)
    
    # Iterate over each item in the JSON array to remove double quotes in descriptions as it is not escaped correctly when the agents is generating the final response
    for item in response:
        # Remove the escaped double quotes from the description
        if 'description' in item:
            item['description'] = item['description'].replace('"', '')

    #print(f"response after the sort:{response}")
          
    #format the response for the agents
    formated_response = llm_utils.generate_json_response(response)

    #formating response to match the agent's expectations
    response_body = {
        'application/json': {
            'body': str(formated_response)
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