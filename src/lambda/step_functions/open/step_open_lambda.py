import json
import boto3
import re
import copy
import traceback

import logging
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
    system_prompt_open = event.get('system_prompt_open', '')
    history_list = event.get('history', [])
    model_id = event.get('model_id', 'anthropic.claude-3-haiku-20240307-v1:0')
    
    #final output message
    output_message = ""
    status_code = 200

    try:

        #------ DEBUG ---------
        logger.debug(f"history list:{history_list}")
        logger.debug(f"system_prompt_open:{system_prompt_open}")

        #calling the LLM
        response_llm = converse_api_call_no_tool(question, history_list, system_prompt_open, bedrock_client, model_id=model_id)
        #extract answer from xml tag
        output_message = extract_answer(response_llm)
        
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
        }

    return {
            'statusCode': status_code,
            'message': json.dumps(output_message),
            'search_output': [],
        }