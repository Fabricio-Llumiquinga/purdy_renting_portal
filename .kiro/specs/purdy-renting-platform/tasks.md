# Implementation Plan: Purdy Renting Platform

## Overview

This implementation plan breaks down the Purdy Renting Platform into incremental coding tasks following a serverless architecture on AWS. The approach starts with shared utilities and infrastructure setup, then builds backend Lambda functions, followed by the React frontend, and concludes with integration wiring and testing. Each task builds upon prior work to ensure no orphaned code.

## Tasks

- [x] 1. Project structure and shared utilities
  - [x] 1.1 Set up backend project structure and dependencies
    - Create the backend directory structure: `backend/handlers/`, `backend/services/`, `backend/utils/`, `backend/tests/`
    - Create `backend/requirements.txt` with dependencies: boto3, pytest, hypothesis, moto, python-dateutil
    - Create `backend/pyproject.toml` or `setup.cfg` for test configuration
    - _Requirements: 10.1, 10.2, 10.4, 10.5_

  - [x] 1.2 Implement shared validators module
    - Create `backend/utils/validators.py` with:
      - `ALLOWED_EXTENSIONS`, `MAX_USER_FILE_SIZE`, `MAX_GENERATED_FILE_SIZE`, `VALID_COMPANIES`, `VALID_STATUSES`, `TERMINAL_STATUSES`, `MAX_OBSERVATION_LENGTH`, `MAX_TEXT_FIELD_LENGTH` constants
      - `validate_file_extension(filename: str) -> bool` — case-insensitive check for .xls, .xlsx, .csv
      - `validate_company(company: str) -> tuple[bool, str | None]` — returns (is_valid, company_code)
      - `validate_status_transition(current_status: str, new_status: str) -> bool` — enforce valid state machine transitions
      - `sanitize_input(value: str, max_length: int) -> str` — reject control chars and script content
      - `format_date_cr(dt: datetime) -> str` — format as dd/MM/yyyy HH:mm
    - _Requirements: 2.8, 3.5, 7.5, 10.4, 9.3_

  - [ ]* 1.3 Write property tests for validators
    - **Property 1: File extension validation consistency**
    - **Validates: Requirements 2.8, 3.5**
    - **Property 2: Company code mapping correctness**
    - **Validates: Requirements 2.3, 5.2**
    - **Property 3: Status transition validity**
    - **Validates: Requirements 7.1, 7.2, 7.3, 7.6**
    - **Property 4: Date formatting round trip**
    - **Validates: Requirements 6.1, 9.3**
    - **Property 5: Input sanitization rejects dangerous content**
    - **Validates: Requirements 10.4**
    - **Property 7: Observation field length enforcement**
    - **Validates: Requirements 7.3**

  - [x] 1.4 Implement shared response and error utilities
    - Create `backend/utils/responses.py` with helper functions for consistent API error/success JSON responses
    - Define error codes enum matching the design document error table (INVALID_FILE_FORMAT, FILE_TOO_LARGE, MISSING_REQUIRED_FIELD, etc.)
    - All error messages in Spanish
    - _Requirements: 9.1, 9.2_

  - [x] 1.5 Set up frontend project structure
    - Initialize React + TypeScript project using Vite
    - Create directory structure: `src/components/Auth/`, `src/components/Request/`, `src/components/Tracking/`, `src/components/Layout/`, `src/services/`, `src/hooks/`, `src/types/`, `src/config/`
    - Install dependencies: @aws-amplify/auth, react-router-dom, axios
    - Create `src/types/index.ts` with `Request`, `CreateRequestPayload`, `PresignedUrlRequest`, `PresignedUrlResponse`, `CreateRequestResponse` interfaces
    - _Requirements: 9.1_

- [x] 2. Checkpoint - Ensure project structure is correct
  - Ensure all tests pass, ask the user if questions arise.

- [x] 3. Backend Lambda functions — File operations
  - [x] 3.1 Implement GetPresignedUrl Lambda handler
    - Create `backend/handlers/get_presigned_url.py`
    - Extract user email from Cognito authorizer claims in the event
    - Validate request body: `fileName`, `contentType`, `fileType` ("listado_precios" or "dai")
    - Validate file extension using `validate_file_extension`
    - Generate unique S3 key: `uploads/{requestId}/{fileType}_{sanitized_filename}`
    - Generate presigned PUT URL with 300-second expiry using boto3 S3 client
    - Return `{ uploadUrl, s3Key }`
    - _Requirements: 3.1, 3.2, 3.5, 10.4_

  - [ ]* 3.2 Write unit tests for GetPresignedUrl handler
    - Test valid file upload request returns presigned URL and unique S3 key
    - Test invalid file extension returns 400 INVALID_FILE_FORMAT
    - Test missing fields return 400 MISSING_REQUIRED_FIELD
    - Use moto to mock S3
    - **Property 8: Presigned URL key uniqueness**
    - **Validates: Requirements 3.2**
    - _Requirements: 3.1, 3.2, 3.5_

  - [x] 3.3 Implement GetDownloadUrl Lambda handler
    - Create `backend/handlers/get_download_url.py`
    - Extract user email from Cognito claims
    - Retrieve request record from DynamoDB by requestId (path parameter)
    - Validate user owns the request (userEmail matches)
    - Validate request has a generatedFileS3Key
    - Generate presigned GET URL with 600-second expiry
    - Return `{ downloadUrl, fileName }`
    - _Requirements: 6.3, 6.5, 10.3, 10.7_

  - [ ]* 3.4 Write unit tests for GetDownloadUrl handler
    - Test successful download URL generation
    - Test 403 when user doesn't own request
    - Test 404 when request not found or no generated file
    - Use moto to mock DynamoDB and S3
    - _Requirements: 6.5, 6.7, 10.3, 10.7_

- [x] 4. Backend Lambda functions — Request management
  - [x] 4.1 Implement CreateRequest Lambda handler
    - Create `backend/handlers/create_request.py`
    - Extract user email from Cognito claims
    - Validate body fields: `listadoPreciosS3Key`, `daiS3Key`, `company`
    - Validate company using `validate_company`
    - Verify S3 files exist using HeadObject (validate file size <= 10 MB)
    - Validate S3 keys contain the user's identifier for ownership
    - Generate UUID v4 for requestId
    - Create DynamoDB record with all required fields, status "Pendiente de Procesar", timestamps in ISO 8601
    - Set GSI1PK = `USER#{userEmail}`, GSI1SK = `CREATED#{createdAt}`
    - Trigger email notification asynchronously (non-blocking)
    - Return `{ requestId, message }` with Spanish confirmation message
    - _Requirements: 2.7, 3.1, 4.1, 4.2, 4.3, 5.1, 10.4_

  - [ ]* 4.2 Write unit tests for CreateRequest handler
    - Test successful request creation with valid inputs
    - Test validation errors for missing fields, invalid company
    - Test 400 when files don't exist in S3
    - Test DynamoDB failure handling (500 response, data preserved)
    - **Property 9: Request record completeness**
    - **Validates: Requirements 4.1, 4.2**
    - Use moto to mock DynamoDB, S3, SES
    - _Requirements: 4.1, 4.2, 4.3, 4.4_

  - [x] 4.3 Implement GetRequests Lambda handler
    - Create `backend/handlers/get_requests.py`
    - Extract user email from Cognito claims
    - Query DynamoDB GSI1 with GSI1PK = `USER#{userEmail}`, sorted by GSI1SK descending
    - Map DynamoDB items to response format
    - Return `{ requests: [...] }` ordered by createdAt DESC
    - _Requirements: 6.1, 6.2, 10.3_

  - [ ]* 4.4 Write unit tests for GetRequests handler
    - Test returns only requests belonging to authenticated user
    - Test ordering by submission date descending
    - Test empty result set
    - **Property 6: User isolation on request queries**
    - **Validates: Requirements 6.2, 10.3**
    - Use moto to mock DynamoDB
    - _Requirements: 6.1, 6.2_

- [x] 5. Backend Lambda functions — Robot API
  - [x] 5.1 Implement UpdateStatus Lambda handler
    - Create `backend/handlers/update_status.py`
    - Validate API key authentication (from event requestContext)
    - Validate body: `requestId`, `status`, optional `observation`
    - Validate status value is in VALID_STATUSES
    - Validate observation length <= 500 chars if provided
    - Retrieve request from DynamoDB; return 404 if not found
    - Check current status is not terminal (Procesado/Failed); return 409 if it is
    - Validate status transition using `validate_status_transition`
    - Update DynamoDB record with new status, observation, and updatedAt timestamp
    - Return `{ message, updatedAt }`
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8_

  - [ ]* 5.2 Write unit tests for UpdateStatus handler
    - Test valid status transitions (Pendiente→Procesando, Procesando→Procesado, Procesando→Failed)
    - Test 404 for non-existent request
    - Test 400 for invalid status values
    - Test 409 for terminal state requests
    - Test 400 for observation exceeding 500 chars
    - Test 401 for missing API key
    - Use moto to mock DynamoDB
    - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_

  - [x] 5.3 Implement UploadGeneratedFile Lambda handler
    - Create `backend/handlers/upload_generated_file.py`
    - Validate API key authentication
    - Validate body: `requestId`, `fileContent` (base64), `fileName`
    - Retrieve request from DynamoDB; return 404 if not found
    - Decode base64 content; return 400 INVALID_BASE64 on failure
    - Validate decoded file size <= 50 MB
    - Upload to S3 at `generated/{requestId}/{fileName}` with SSE-S3 encryption
    - Update DynamoDB record with `generatedFileName` and `generatedFileS3Key`
    - If S3 fails, return 500 without updating DynamoDB
    - Return `{ message, s3Key }`
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

  - [ ]* 5.4 Write unit tests for UploadGeneratedFile handler
    - Test successful file upload and DynamoDB update
    - Test 400 for malformed base64
    - Test 404 for non-existent request
    - Test 400 for file exceeding 50 MB
    - Test S3 failure doesn't update DynamoDB
    - Use moto to mock S3, DynamoDB
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_

- [x] 6. Email notification service
  - [x] 6.1 Implement notification service
    - Create `backend/services/notification_service.py`
    - Implement `send_submission_confirmation(recipient_email, user_name, company_name, company_code, submission_date) -> bool`
    - Format email subject: "Listado Precios - {company_code}"
    - Format email body with user name, submission date (dd/MM/yyyy HH:mm), company name
    - Implement retry logic: up to 3 attempts with exponential backoff (1s, 2s, 4s)
    - Return True on success, False after all retries exhausted
    - Log failures for observability
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [ ]* 6.2 Write unit tests for notification service
    - Test successful email send
    - Test retry logic on transient SES failures
    - Test failure after 3 retries returns False
    - Test email subject format for both company codes
    - **Property 10: Email subject format correctness**
    - **Validates: Requirements 5.2**
    - Use moto to mock SES
    - _Requirements: 5.2, 5.3, 5.4_

- [x] 7. Checkpoint - Ensure all backend tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Frontend authentication and layout
  - [x] 8.1 Configure AWS Amplify Auth with Cognito
    - Create `src/config/aws-config.ts` with Cognito User Pool configuration (pool ID, client ID, domain, redirect URIs)
    - Configure OIDC federation with Microsoft Entra ID
    - Set up token lifetime handling (60 min access, 30 day refresh)
    - _Requirements: 1.1, 1.2, 1.5_

  - [x] 8.2 Implement authentication hook and protected route
    - Create `src/hooks/useAuth.ts` hook that:
      - Manages authentication state (isAuthenticated, user, loading)
      - Handles login redirect to Cognito Hosted UI
      - Handles token refresh before expiry
      - Detects session expiration and triggers re-auth
    - Create `src/components/Auth/ProtectedRoute.tsx` that redirects unauthenticated users to login
    - _Requirements: 1.1, 1.2, 1.4, 1.6_

  - [x] 8.3 Implement layout components
    - Create `src/components/Layout/Header.tsx` with app title and user info display (Spanish labels)
    - Create `src/components/Layout/ErrorBoundary.tsx` for graceful error handling with Spanish error messages
    - Set up React Router with protected routes for the main views
    - _Requirements: 9.1, 1.3_

- [x] 9. Frontend request creation flow
  - [x] 9.1 Implement file upload service
    - Create `src/services/fileService.ts` with:
      - `getPresignedUrl(fileName, contentType, fileType)` — calls POST /requests/presigned-url
      - `uploadFileToS3(presignedUrl, file)` — PUT to presigned URL with progress tracking
    - Include proper Authorization header with Cognito access token
    - Handle upload errors and return meaningful error state
    - _Requirements: 3.1, 3.3, 3.4_

  - [x] 9.2 Implement FileUpload component
    - Create `src/components/Request/FileUpload.tsx`
    - Accept props: `label`, `fileType`, `onFileSelected`, `error`
    - Validate file extension (.xls, .xlsx, .csv) on selection
    - Validate file size <= 10 MB on selection
    - Display upload progress indicator
    - Show validation errors inline in Spanish
    - Allow cancel of in-progress upload
    - _Requirements: 2.2, 2.5, 2.8, 3.4, 3.5, 9.1, 9.2_

  - [x] 9.3 Implement CompanySelector component
    - Create `src/components/Request/CompanySelector.tsx`
    - Render dropdown with exactly two options: "Purdy Motor" and "Automotriz"
    - Labels and placeholder text in Spanish
    - _Requirements: 2.3, 2.6, 9.1_

  - [x] 9.4 Implement RequestForm component
    - Create `src/components/Request/RequestForm.tsx`
    - Compose FileUpload (×2) and CompanySelector components
    - Implement form state management
    - Enable "Enviar solicitud" button only when both files attached and company selected
    - On submit: call fileService to upload files, then requestService to create request
    - Display confirmation message with requestId on success (Spanish)
    - Display validation errors inline on failure (Spanish)
    - Preserve form data on error (do not clear the form)
    - _Requirements: 2.1, 2.4, 2.5, 2.6, 2.7, 4.3, 9.1, 9.2_

  - [x] 9.5 Implement request service
    - Create `src/services/requestService.ts` with:
      - `createRequest(payload: CreateRequestPayload)` — calls POST /requests
      - `getRequests()` — calls GET /requests
      - `getDownloadUrl(requestId)` — calls GET /requests/{id}/download
    - Include Authorization header with Cognito access token
    - Map error responses to Spanish user-facing messages
    - _Requirements: 2.7, 6.1, 6.5_

- [x] 10. Frontend request tracking view
  - [x] 10.1 Implement RequestTable component
    - Create `src/components/Tracking/RequestTable.tsx`
    - Display columns: Fecha, Tipo Solicitud, Empresa, Nombre Listado Generado, Estado
    - Format dates using dd/MM/yyyy HH:mm format
    - Render Generated File name as clickable download link when available
    - Show empty value when no generated file exists
    - Order requests by submission date descending
    - Show loading state and error message in Spanish on failure
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.6, 9.1, 9.3_

  - [x] 10.2 Implement RequestRow component and download logic
    - Create `src/components/Tracking/RequestRow.tsx`
    - Render individual request data with proper formatting
    - Handle download click: call getDownloadUrl, then trigger browser download
    - Show error toast in Spanish if download fails
    - _Requirements: 6.3, 6.5, 6.7, 9.1_

  - [x] 10.3 Implement useRequests hook
    - Create `src/hooks/useRequests.ts`
    - Manage request list state, loading, and error states
    - Fetch requests on mount using requestService
    - Provide refresh function for after new request creation
    - _Requirements: 6.1, 6.2_

- [x] 11. Checkpoint - Ensure frontend components render correctly
  - Ensure all tests pass, ask the user if questions arise.

- [ ] 12. Frontend tests
  - [ ]* 12.1 Write Jest unit tests for frontend components
    - Test FileUpload validates extensions and size
    - Test CompanySelector renders both options
    - Test RequestForm enables submit button only when all fields valid
    - Test RequestForm preserves data on error
    - Test RequestTable renders columns and formats dates correctly
    - Test RequestRow renders download link only when generated file exists
    - Test useAuth hook handles session expiration
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 6.1, 6.3, 6.4, 9.3_

  - [ ]* 12.2 Write Jest unit tests for frontend services
    - Test fileService handles presigned URL flow
    - Test requestService maps API errors to Spanish messages
    - Test auth service token refresh logic
    - _Requirements: 3.1, 9.2_

- [x] 13. Integration wiring and final assembly
  - [x] 13.1 Create SAM/CDK infrastructure template
    - Create `infrastructure/template.yaml` (SAM) or CDK stack defining:
      - DynamoDB table with GSI1 (UserEmail-CreatedAt)
      - S3 bucket with SSE-S3, CORS config, public access blocked
      - API Gateway REST API with Cognito Authorizer and API Key usage plan
      - Lambda functions with IAM roles (least privilege)
      - SES verified identity configuration
      - Cognito User Pool with Entra ID OIDC federation
      - CloudFront distribution for React SPA
    - _Requirements: 10.1, 10.2, 10.5, 1.1, 1.2_

  - [x] 13.2 Wire API Gateway routes to Lambda handlers
    - Define all 6 API routes per design:
      - POST /requests/presigned-url → GetPresignedUrl (Cognito auth)
      - POST /requests → CreateRequest (Cognito auth)
      - GET /requests → GetRequests (Cognito auth)
      - GET /requests/{id}/download → GetDownloadUrl (Cognito auth)
      - PUT /requests/{id}/status → UpdateStatus (API Key auth)
      - POST /requests/{id}/file → UploadGeneratedFile (API Key auth)
    - Configure request/response models and CORS headers
    - _Requirements: 7.7, 7.8, 10.1, 10.6_

  - [x] 13.3 Wire frontend to API Gateway
    - Create `src/config/api.ts` with base URL and interceptor for auth token injection
    - Ensure all service calls use the configured base URL
    - Configure CORS on API Gateway for frontend domain
    - Test end-to-end connectivity from React → API Gateway → Lambda
    - _Requirements: 1.5, 10.2_

- [ ] 14. Integration tests
  - [ ]* 14.1 Write backend integration tests
    - Test full request creation flow: presigned URL → S3 upload → CreateRequest → verify DynamoDB record
    - Test Robot flow: UpdateStatus → UploadGeneratedFile → verify state
    - Test access control: user A cannot query user B's requests
    - Test error scenarios: S3 failure, DynamoDB failure
    - Use moto for AWS service mocking
    - _Requirements: 3.1, 4.1, 6.2, 7.1, 8.1, 10.3_

  - [ ]* 14.2 Write Cypress E2E test stubs
    - Create Cypress configuration and test structure
    - Write test stub for login flow (stubbed Cognito/Entra)
    - Write test stub for request creation with file upload
    - Write test stub for request tracking table display
    - Write test stub for generated file download
    - _Requirements: 1.1, 2.7, 6.1, 6.5_

- [x] 15. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties defined in the design document
- Unit tests validate specific examples and edge cases
- Backend uses Python with pytest + Hypothesis for property-based testing
- Frontend uses TypeScript with Jest + React Testing Library
- All user-facing text must be in Spanish per Requirement 9
- Infrastructure template (Task 13.1) can use either AWS SAM or AWS CDK based on team preference

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.5"] },
    { "id": 1, "tasks": ["1.2", "1.4"] },
    { "id": 2, "tasks": ["1.3", "3.1", "3.3", "4.3", "8.1"] },
    { "id": 3, "tasks": ["3.2", "3.4", "4.1", "4.4", "8.2", "8.3"] },
    { "id": 4, "tasks": ["4.2", "5.1", "5.3", "6.1", "9.1", "9.3"] },
    { "id": 5, "tasks": ["5.2", "5.4", "6.2", "9.2", "9.5"] },
    { "id": 6, "tasks": ["9.4", "10.3"] },
    { "id": 7, "tasks": ["10.1", "10.2"] },
    { "id": 8, "tasks": ["12.1", "12.2", "13.1"] },
    { "id": 9, "tasks": ["13.2", "13.3"] },
    { "id": 10, "tasks": ["14.1", "14.2"] }
  ]
}
```
