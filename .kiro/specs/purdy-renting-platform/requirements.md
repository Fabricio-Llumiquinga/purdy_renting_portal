# Requirements Document

## Introduction

Purdy Renting is a web platform for managing price list requests within the Purdy Motor and Automotriz companies in Costa Rica. The platform enables users to submit requests with file attachments, track request status through an RPA-driven workflow, and receive email notifications. The system integrates with Microsoft Entra ID via AWS Cognito for corporate authentication, uses AWS Lambda for backend services, DynamoDB for data persistence, and S3 for file storage.

## Glossary

- **Platform**: The Purdy Renting web application comprising frontend (React), backend (AWS Lambda/Python), database (DynamoDB), and file storage (S3)
- **User**: An authenticated corporate employee who submits and tracks price list requests
- **Request**: A submission record containing attached files, company selection, and status metadata
- **Company_Selector**: The dropdown UI component allowing selection of "Purdy Motor" or "Automotriz"
- **Company_Code**: The abbreviated identifier for a company ("PM" for Purdy Motor, "AUTO" for Automotriz)
- **Listado_Precios_File**: The price list file attached by the User during request submission
- **DAI_File**: The DAI list file attached by the User during request submission
- **Robot**: The external RPA system that processes submitted requests and generates output files
- **Generated_File**: The Excel file produced by the Robot after processing a request
- **Auth_Service**: The authentication layer combining Microsoft Entra ID and AWS Cognito for corporate login
- **Notification_Service**: The email delivery component that sends notifications upon request submission
- **Request_Tracking_View**: The UI component displaying a table of all requests with their current status
- **API_Gateway**: The AWS API Gateway that exposes backend services to the frontend and the Robot

## Requirements

### Requirement 1: Corporate Authentication

**User Story:** As a corporate employee, I want to log in using my corporate Microsoft account, so that I can securely access the platform without managing separate credentials.

#### Acceptance Criteria

1. WHEN a User navigates to the Platform, THE Auth_Service SHALL redirect unauthenticated users to the Microsoft Entra ID login page via AWS Cognito within 2 seconds
2. WHEN the User completes authentication with Microsoft Entra ID, THE Auth_Service SHALL issue a valid session token with a lifetime of 60 minutes and redirect the User to the Platform home page
3. IF the User provides invalid credentials, THEN THE Auth_Service SHALL display an error message in Spanish indicating authentication failure
4. WHEN a User session token is expired, THE Platform SHALL redirect the User to the login page for re-authentication
5. THE Auth_Service SHALL validate the session token on every API request to the backend
6. IF the session token validation fails on an API request, THEN THE API_Gateway SHALL return a 401 error response and THE Platform SHALL redirect the User to the login page

### Requirement 2: Request Creation

**User Story:** As a User, I want to create a new price list request, so that I can submit files for processing by the RPA system.

#### Acceptance Criteria

1. WHEN the User clicks the "Crear nueva solicitud" button, THE Platform SHALL display the request submission form
2. THE Platform SHALL display a file attachment section with two upload fields: one labeled "Listado Precios" and one labeled "Listado DAI", each accepting files in .xls, .xlsx, or .csv format with a maximum size of 10 MB per file
3. THE Platform SHALL display a Company_Selector dropdown with exactly two options: "Purdy Motor" and "Automotriz"
4. WHEN the User has attached both files and selected a company, THE Platform SHALL enable the "Enviar solicitud" button
5. IF the User attempts to submit without attaching both files, THEN THE Platform SHALL display a validation error in Spanish indicating the missing attachment and SHALL keep the form open with previously entered data preserved
6. IF the User attempts to submit without selecting a company, THEN THE Platform SHALL display a validation error in Spanish indicating company selection is required and SHALL keep the form open with previously entered data preserved
7. WHEN the User clicks the "Enviar solicitud" button with all required fields completed, THE Platform SHALL submit the request and display a confirmation message in Spanish indicating the request was created successfully
8. IF a file upload fails due to unsupported format or exceeding the 10 MB size limit, THEN THE Platform SHALL display a validation error in Spanish indicating the reason for rejection and SHALL not allow form submission until a valid file is provided

### Requirement 3: File Upload to S3

**User Story:** As a User, I want my attached files to be stored securely, so that they are available for processing by the Robot.

#### Acceptance Criteria

1. WHEN the User submits a request with the Listado_Precios_File and DAI_File attached, THE Platform SHALL upload both files to S3
2. THE Platform SHALL store each file in S3 using a unique key that includes the request identifier and original filename
3. IF a file upload to S3 fails, THEN THE Platform SHALL display an error message in Spanish, revert any already-uploaded file from the same request, and prevent the request from being created
4. IF an uploaded file exceeds 10 MB, THEN THE Platform SHALL reject the file, display an error message in Spanish indicating the size limit, and prevent the request from being submitted
5. THE Platform SHALL accept only files with .xlsx, .xls, or .csv extensions for both Listado_Precios_File and DAI_File
6. IF either the Listado_Precios_File or the DAI_File is not attached, THEN THE Platform SHALL display an error message in Spanish indicating the missing file and prevent the request from being submitted

### Requirement 4: Request Persistence

**User Story:** As a User, I want my submitted request to be stored permanently, so that I can track its progress later.

#### Acceptance Criteria

1. WHEN the User submits a valid request, THE Platform SHALL create a record in DynamoDB containing: request identifier, user email, company selection, S3 file references, submission timestamp, and status set to "Pendiente de Procesar"
2. WHEN a new request is submitted, THE Platform SHALL generate a unique identifier in UUID format for that request
3. WHEN the request record is created successfully, THE Platform SHALL display a confirmation message in Spanish to the User that includes the generated request identifier
4. IF the Platform fails to persist the request record in DynamoDB, THEN THE Platform SHALL display an error message in Spanish indicating that the submission could not be completed and SHALL not discard the data entered by the User

### Requirement 5: Email Notification on Submission

**User Story:** As a User, I want to receive an email notification when I submit a request, so that I have confirmation of my submission.

#### Acceptance Criteria

1. WHEN a request is submitted successfully, THE Notification_Service SHALL send an email notification to the email address associated with the submitting User within 30 seconds of submission
2. THE Notification_Service SHALL set the email subject to "Listado Precios - [Company_Code]" where Company_Code is "PM" for Purdy Motor and "AUTO" for Automotriz
3. THE Notification_Service SHALL include in the email body: the name of the User who submitted the request, the submission date in "dd/MM/yyyy HH:mm" format, and the selected company full name
4. IF the email notification fails to send after 3 retry attempts, THEN THE Notification_Service SHALL log the failure and display a warning message to the User indicating that the confirmation email could not be sent, without blocking or rolling back the request submission
5. IF the submitting User does not have an email address on file, THEN THE Notification_Service SHALL skip the email notification and log a warning indicating no recipient address was available

### Requirement 6: Request Tracking View

**User Story:** As a User, I want to view the status of my submitted requests, so that I can monitor their processing progress.

#### Acceptance Criteria

1. WHEN the User navigates to the tracking section, THE Request_Tracking_View SHALL display a table with columns: Fecha (formatted as dd/MM/yyyy HH:mm), Tipo Solicitud, Empresa, Nombre Listado Generado, Estado
2. THE Request_Tracking_View SHALL display all requests submitted by the authenticated User ordered by submission date descending
3. WHEN a request has a Generated_File associated, THE Request_Tracking_View SHALL display the file name as a clickable link in the "Nombre Listado Generado" column
4. WHEN a request does not have a Generated_File associated, THE Request_Tracking_View SHALL display an empty value in the "Nombre Listado Generado" column with no clickable link
5. WHEN the User clicks on the Generated_File name, THE Platform SHALL initiate a download of the file from S3
6. IF the tracking data fails to load, THEN THE Request_Tracking_View SHALL display an error message in Spanish indicating that requests could not be retrieved
7. IF the Generated_File download fails, THEN THE Platform SHALL display an error message in Spanish indicating that the file could not be downloaded

### Requirement 7: RPA Status Update API

**User Story:** As the Robot, I want to update the processing status of a request, so that Users can track progress in real time.

#### Acceptance Criteria

1. WHEN the Robot sends a status update with value "Procesando" for a valid request identifier, THE API_Gateway SHALL update the request status to "Procesando" in DynamoDB and record the timestamp of the status change
2. WHEN the Robot sends a status update with value "Procesado" for a valid request identifier, THE API_Gateway SHALL update the request status to "Procesado" in DynamoDB and record the timestamp of the status change
3. WHEN the Robot sends a status update with value "Failed" for a valid request identifier, THE API_Gateway SHALL update the request status to "Failed" in DynamoDB, store the provided error detail (maximum 500 characters) in an observation field, and record the timestamp of the status change
4. IF the Robot sends a request identifier that does not match any existing request in DynamoDB, THEN THE API_Gateway SHALL return a 404 error response
5. IF the Robot sends a status value other than "Procesando", "Procesado", or "Failed", THEN THE API_Gateway SHALL return a 400 error response indicating the allowed status values
6. IF the Robot sends a status update for a request that is already in "Procesado" or "Failed" status, THEN THE API_Gateway SHALL return a 409 error response indicating that the request is already in a terminal state
7. THE API_Gateway SHALL authenticate Robot requests using an API key or service credential
8. IF the Robot sends a request without a valid API key or service credential, THEN THE API_Gateway SHALL return a 401 error response and not process the status update

### Requirement 8: Robot File Upload API

**User Story:** As the Robot, I want to upload the generated Excel file for a processed request, so that Users can access the result.

#### Acceptance Criteria

1. WHEN the Robot sends a base64-encoded file with a request identifier, THE API_Gateway SHALL decode the file and store it in S3
2. WHEN the file is successfully stored in S3, THE API_Gateway SHALL update the DynamoDB record with the "Nombre Listado Generado" value provided by the Robot
3. IF the base64 payload is malformed, THEN THE API_Gateway SHALL return a 400 error response indicating invalid file encoding
4. IF the request identifier does not exist, THEN THE API_Gateway SHALL return a 404 error response
5. IF the decoded file size exceeds 50 MB, THEN THE API_Gateway SHALL reject the upload and return a 400 error response indicating the file exceeds the maximum allowed size
6. IF the S3 storage operation fails, THEN THE API_Gateway SHALL return a 500 error response indicating the file could not be stored and SHALL NOT update the DynamoDB record

### Requirement 9: Spanish Language Interface

**User Story:** As a Costa Rican corporate employee, I want the platform displayed in Spanish, so that I can use it in my native language.

#### Acceptance Criteria

1. THE Platform SHALL display all UI labels, messages, buttons, and notifications in Spanish
2. THE Platform SHALL display all error messages and validation feedback in Spanish
3. THE Platform SHALL format dates using the "dd/MM/yyyy HH:mm" format
4. THE Platform SHALL use the decimal comma and period as thousands separator for numeric values following Costa Rican locale conventions

### Requirement 10: Security and Access Control

**User Story:** As a platform administrator, I want the system to enforce security best practices, so that corporate data remains protected.

#### Acceptance Criteria

1. THE API_Gateway SHALL require a valid authentication token issued by the Auth_Service for all endpoints except Robot-authenticated endpoints (which use API key or service credential as defined in Requirement 7)
2. THE Platform SHALL transmit all data over HTTPS
3. THE Platform SHALL enforce that a User can only view and download requests and associated files submitted by that same User
4. THE API_Gateway SHALL validate all input parameters against expected type, length (maximum 1000 characters for text fields), and format before processing, and SHALL reject any parameter containing unescaped control characters or script content
5. THE Platform SHALL store S3 files with server-side encryption enabled
6. IF an unauthenticated request is received on a protected endpoint, THEN THE API_Gateway SHALL return a 401 error response
7. IF an authenticated User attempts to access a request that was not submitted by that User, THEN THE API_Gateway SHALL return a 403 error response without revealing the existence or details of the requested resource
