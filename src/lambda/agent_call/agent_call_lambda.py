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

    #static plug for the moment. for test
    
    response = {
        "text": "Here is a list of popular action movies ordered by popularity:",
        "Titles": [
            {
                "tmdb_id": 245891,
                "original_title": "John Wick",
                "genres": "Action,Thriller",
                "description": "Ex-lunatic John Wick comes off his meds to track down the bounders that killed his dog and made off with his self-respect",
                "keywords": "hitman,russian mafia,revenge,murder,gangster,dog,retired,widower",
                "director": "Chad Stahelski",
                "year": 2014,
                "popularity": 183.9,
                "vote_average": 7.0,
                "vote_average_bins": "High"
            },
            {
                "tmdb_id": 680,
                "original_title": "Pulp Fiction",
                "genres": "Thriller,Crime",
                "description": "A burger-loving hit man, his philosophical partner, a drug-addled gangster's moll and a washed-up boxer converge in this sprawling, comedic crime caper. Their adventures unfurl in three stories that ingeniously trip back and forth in time.",
                "keywords": "transporter,brothel,drug dealer,boxer,massage,stolen money,crime boss,dance contest,junkyard,kamikaze,ambiguous ending,briefcase,redemption,heirloom,pulp fiction,reference to al green,theft,brutality",
                "director": "Quentin Tarantino",
                "year": 1994,
                "popularity": 141.0,
                "vote_average": 8.3,
                "vote_average_bins": "Very High"
            },
            ]
    }

    return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,GET'
            },
            "body": json.dumps({"message": response})
        }
