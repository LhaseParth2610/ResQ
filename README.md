#ResQ - Disaster Management Platform

Overview
ResQ is a real-time disaster management platform designed to bridge the gap between communities and emergency response services. By enabling instant disaster reporting and crowd-sourced danger zone mapping, ResQ ensures that critical information reaches authorities in real time—improving response efficiency and saving lives.

Features
Instant Disaster Reporting: Users can report incidents like floods, earthquakes, and fires in real time. 

![Image](https://github.com/user-attachments/assets/ca92dd4c-12e1-47e2-bedb-b8561bc2fc6f)

Crowd-Sourced Danger Zones:
Visual mapping of high-risk areas to improve situational awareness.
helps both users and authorities get insights on the actual on ground situation also helps in identifying emerging hazards, enabling proactive disaster management and evacuation planning.

![Image](https://github.com/user-attachments/assets/aec4199a-f9e6-449a-a0b0-6d7cb08a47fa)

Rapid alerts via SOS and broadcast messaging.These SOS messages contain users details like name,emergency contact number and ofcourse the users current location in longitudes and latitudes,this information is sent directly to the authorities 

Safe Routes:
Dynamically maps secure paths away from danger zones, guiding users to safety during emergencies.
Updates in real time to reflect changing conditions on the ground.

![Image](https://github.com/user-attachments/assets/46c307e9-31c6-4ae6-b255-c6a06d5363b0)



Role-Based Efficiency:

Dual interfaces for users and authorities to ensure secure and efficient communication and action.
Community Empowerment:

Offers emergency resources, public notices, donation options, and volunteer opportunities to build community resilience.

How It Works?

Reporting:
Users submit disaster reports via an intuitive web interface.
Coordination:
Authorities receive instant alerts and mapped data to coordinate a rapid response.

Safe Navigation:
The Safe Routes feature provides users with updated, secure paths to avoid danger areas during emergencies.

Technical Details
Backend: Flask
Database: PostgreSQL
Mapping: Leaflet integrated with OpenStreetMap
UI Design: Professional and accessible, featuring secure authentication and a consistent theme

Installation & Setup
Clone the Repository:
git clone https://github.com/yourusername/ResQ.git

Navigate to the Project Directory:
cd ResQ

Install Dependencies:

pip install -r requirements.txt

Configure Environment Variables:
Update your .env file with the required settings (e.g., database URL, secret keys).
Run the Application:
flask run
Future Enhancements
AI-based disaster prediction and risk assessment.
Mobile application integration for better accessibility.
Multilingual support for broader reach.
License
[Insert license information here.]

Contact
For more details or collaboration opportunities, please reach out:
Your Name
Email: [your.email@example.com]
GitHub: github.com/yourusername

