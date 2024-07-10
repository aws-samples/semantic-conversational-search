import json
import boto3
from utils import llm_utils
import time
import os
import re
import copy
import traceback

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

from opensearchpy import (
    AWSV4SignerAuth
)

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

#converse API call
def converse_api_call_no_tool(question, history_list, system_prompt, bedrock_client, model_id="anthropic.claude-3-haiku-20240307-v1:0"):
    
    messages = []

    if history_list:
        messages = copy.deepcopy(history_list)
    
    user_message = {
        "role": "user",
        "content": [
            { "text": json.dumps(question) } 
        ],
    }
    messages.append(user_message)

    response = bedrock_client.converse(
        modelId=model_id,
        messages=messages,
        inferenceConfig={
            "maxTokens": 2000,
            "temperature": 0,
            "topP": 1
        },
        system=[{"text": json.dumps(system_prompt)}]
    )
    
    #extract message
    response_message = response['output']['message']["content"]

    return response_message[0]["text"]



#handler
def lambda_handler(event, context):

    #retrieve parameters
    question = event.get('question', '')
    system_prompt_extract_movie_from_question = event.get('system_prompt_extract_movie_from_question', '')
    system_prompt_extract_movie_from_history = event.get('system_prompt_extract_movie_from_history', '')
    system_prompt_specific = event.get('system_prompt_specific', '')
    history_list = event.get('history', [])
    index_name = event.get('index_name', '')
    os_host = event.get('os_host', '')
    model_id = event.get('model_id', 'anthropic.claude-3-haiku-20240307-v1:0')
    
    data_columns = ['tmdb_id', 'original_language', 'original_title', 'description', 'genres', 'year', 'keywords', 'director', 'actors', 'popularity', 'popularity_bins',
                  'vote_average', 'vote_average_bins']
    

    #final output
    output_message = ""
    movie_name = ""
    status_code = 200

    try:
        #------ DEBUG ---------
        logger.debug(f"history list:{history_list}")
        logger.debug(f"system_prompt_specific:{system_prompt_specific}")

        #history list is empty so we need to extract the movie name from the question
        if not history_list:
            #extract movie name from question
            response = converse_api_call_no_tool(question, [], system_prompt_extract_movie_from_question, bedrock_client, model_id=model_id)
            movie_name = extract_answer(response)

        # if history list is not empty, we need to take into consideration for the question
        else:
            #extract movie name from question
            response = converse_api_call_no_tool(question, history_list, system_prompt_extract_movie_from_history, bedrock_client, model_id=model_id)
            movie_name = extract_answer(response)

        if movie_name:
            #building the filter for opensearch
            prop_value_list = [{"original_title": movie_name}]

            #retrieve the information about the movie using standard search
            #get region
            region_name = os.environ.get('AWS_REGION')
            #auth object required to connect to opensearch
            credentials = boto3.Session().get_credentials()
            auth = AWSV4SignerAuth(credentials, region_name, 'aoss')

            #connecting to opensearch serverless
            os_client = llm_utils.connect_to_aoss(auth, os_host)

            #querying opensearch
            start_time = time.time()
            response_aoss = llm_utils.standard_query_opensearch(prop_value_list, os_client, index_name, data_columns, k=1)
            end_time = time.time()
            execution_time = end_time - start_time

            logger.debug(f"Querying OpenSearch took {execution_time:.6f} seconds.")

            response_aoss_str = json.dumps(response_aoss)

            logger.debug(f"response_aoss:{response_aoss_str}")

            #injecting the documents into the prompt
            system_prompt_specific = system_prompt_specific.replace("{context}", response_aoss_str)

            #now we giving the movie information to the LLM to generate a response
            response_llm = converse_api_call_no_tool(question, history_list, system_prompt_specific, bedrock_client, model_id=model_id)
            #extract answer from xml tag
            output_message = extract_answer(response_llm)

            logger.debug(f"original answer:{response_llm}")
            logger.debug(f"extracted answer:{output_message}")

             #default response if nothing can be extracted
            if not output_message:
                output_message = response_llm
                status_code = 500

    except Exception as e:
        logger.error(f"Error: {e}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'message': str(e),
            'search_output': [],
            'movie_name':movie_name
        }
    
    return {
            'statusCode': status_code,
            'message': json.dumps(output_message),
            'search_output': [],
            'movie_name':movie_name
            }