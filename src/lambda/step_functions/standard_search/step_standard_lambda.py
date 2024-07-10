import json
import boto3
import os
from utils import llm_utils
import time

from opensearchpy import (
    AWSV4SignerAuth
)

import logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#bedrock client
bedrock_client = boto3.client('bedrock-runtime')

#handler
def lambda_handler(event, context):

    #retrieve parameters
    question = event.get('question', '')
    index_name = event.get('index_name', '')
    os_host = event.get('os_host', '')
    system_prompt = event.get('system_prompt', '')
    tool_list = event.get('tool_list', [])
    number_results = event.get('number_results', 10)
    
    #get region
    region_name = os.environ.get('AWS_REGION')

    #columns names from the opensearch index
    data_columns = ['tmdb_id', 'original_language', 'original_title', 'description', 'genres', 'year', 'keywords', 'director', 'actors', 'popularity', 'popularity_bins',
                  'vote_average', 'vote_average_bins']
    
    status_code = 200
    search_output = []
    output_message = ""

    try:
        #------ Function Calling LLM call --------
        messages = []

        user_message = {
            "role": "user",
            "content": [
                { "text": json.dumps(question) } 
            ],
        }
        messages.append(user_message)

        response_tool = bedrock_client.converse(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            messages=messages,
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0,
                "topP": 1
            },
            toolConfig={
                "tools": tool_list
            },
            system=[{"text": json.dumps(system_prompt)}]
        )
        
        #we retrieve the list of filters from the tool
        tool_output = ""

        #extract message
        response_tool_message = response_tool['output']['message']["content"]

        for elt in response_tool_message:
            if "toolUse" in elt:
                tool_output = elt["toolUse"]["input"]
            
        if tool_output:
            prop_value_list = []
            if isinstance(tool_output, list):
                prop_value_list = tool_output
            else:
                prop_value_list = [tool_output]

            #---------- OpenSearch call -----------
            #auth object required to connect to opensearch
            credentials = boto3.Session().get_credentials()
            auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

            #connecting to opensearch serverless
            os_client = llm_utils.connect_to_aoss(auth, os_host)

            #querying opensearch
            start_time = time.time()
            search_output = llm_utils.standard_query_opensearch(prop_value_list, os_client, index_name, data_columns, k=number_results)
            end_time = time.time()
            execution_time = end_time - start_time

            logger.debug(f"Querying OpenSearch took {execution_time:.6f} seconds.")

            statusCode = 200
            output_message = f"Here is a list of movies in response to the question:{question}"

        else:
            output_message = ""
            status_code = 500
            search_output = []

    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'message': str(e),
            'search_output': [],
            'question': question
        }
    
    return {
            'statusCode': status_code,
            'search_output': search_output,
            'question': question,
            'message': output_message
        }