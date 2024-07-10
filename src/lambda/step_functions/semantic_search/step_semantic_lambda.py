import json
import boto3
import os
from utils import llm_utils
import time
import re

from opensearchpy import (
    AWSV4SignerAuth
)

import logging
import traceback
logger = logging.getLogger()
logger.setLevel(logging.INFO)

#bedrock client
bedrock_client = boto3.client('bedrock-runtime')

#extract answer from tags
def extract_answer(text, tag="answer"):
    pattern = f'<{tag}>(.*?)</{tag}>'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return match.group(1)
    else:
        return None

#handler
def lambda_handler(event, context):

    #retrieve parameters
    question = event.get('question', '')
    index_name = event.get('index_name', '')
    os_host = event.get('os_host', '')
    system_prompt = event.get('system_prompt', '')
    prefill = event.get('prefill', '')
    number_results = event.get('number_results', 10)

    output_message = ""
    status_code = 200
    optimised_query = ""
    search_output = []

    try:
        #------ Query optimisation --------
        messages = []

        user_message = {
            "role": "user",
            "content": [
                { "text": json.dumps(question) } 
            ],
        }
        messages.append(user_message)

        if prefill != "": 
            assistant_prefill_message = {
                "role": "assistant",
                "content": [
                    { "text": prefill }
                ],
            }
            messages.append(assistant_prefill_message)

        response_optim = bedrock_client.converse(
            modelId="anthropic.claude-3-haiku-20240307-v1:0",
            messages=messages,
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0,
                "topP": 1
            },
            system=[{"text": json.dumps(system_prompt)}]
        )

        #extract message
        response_message = response_optim['output']['message']

        #extract the model response
        full_response_message = prefill + response_message["content"][0]["text"]

        optimised_query = extract_answer(full_response_message, tag="answer")

        if optimised_query:
            #------ OpenSearch call --------
            #get region
            region_name = os.environ.get('AWS_REGION')

            #columns names from the opensearch index
            data_columns = ['tmdb_id', 'original_language', 'original_title', 'description', 'genres', 'year', 'keywords', 'director', 'actors', 'popularity', 'popularity_bins',
                        'vote_average', 'vote_average_bins']
            
            #auth object required to connect to opensearch
            credentials = boto3.Session().get_credentials()
            auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

            #connecting to opensearch serverless
            os_client = llm_utils.connect_to_aoss(auth, os_host)

            #querying opensearch
            start_time = time.time()
            os_response = llm_utils.query_opensearch(optimised_query, os_client, index_name, data_columns, embedding_model="cohere", k=number_results)
            end_time = time.time()
            execution_time = end_time - start_time

            logger.debug(f"Querying OpenSearch took {execution_time:.6f} seconds.")

            #extract object from os response
            search_output = llm_utils.extract_response_from_os_response(os_response)

            output_message = f"Here is a list of movies in response to the question: {question}"
        else:
            output_message = "Optimising question -{question}- failed"
            optimised_query = ""
            status_code = 500

    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'search_output': [],
            'question': question,
            'optimised_query': "",
            'message':str(e)
        }

    return {
            'statusCode': status_code,
            'search_output': search_output,
            'question': question,
            'optimised_query': optimised_query,
            'message':output_message
        }