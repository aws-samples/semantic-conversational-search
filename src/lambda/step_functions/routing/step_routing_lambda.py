import json
import boto3
import re

import logging
logger = logging.getLogger()
logger.setLevel(logging.DEBUG)

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

    question = event.get('question', '')
    history_list = event.get('history', [])
    system_prompt = event.get('system_prompt', '')
    prefill = event.get('prefill', '')
    model_id = event.get('model_id', 'anthropic.claude-3-haiku-20240307-v1:0')

    try:

        user_message = {
            "role": "user",
            "content": [
                { "text": json.dumps(question) } 
            ],
        }

        history_list.append(user_message)

        if prefill != "": 
            assistant_prefill_message = {
                "role": "assistant",
                "content": [
                    { "text": prefill }
                ],
            }
            history_list.append(assistant_prefill_message)

        response = bedrock_client.converse(
            modelId=model_id,
            messages=history_list,
            inferenceConfig={
                "maxTokens": 2000,
                "temperature": 0,
                "topP": 1
            },
            system=[{"text": json.dumps(system_prompt)}]
        )

        #extract message
        response_message = response['output']['message']

        logger.debug(f"routing raw response_message:{response_message}")

        #extract the model response
        category = prefill + response_message["content"][0]["text"]

        extracted_category = extract_answer(category)

        output_message = f"question is categorised as {extracted_category}"

    except Exception as e:
        logger.error(f"Error: {e}")
        return {
            'statusCode': 500,
            'category': "",
            'question': question,
            'history': history_list,
            'message': json.dumps(f'Error: {e}')
        }
    
    return {
        'statusCode': 200,
        'category': extracted_category,
        'question': question,
        'history': history_list,
        'message':output_message
    }